/*
 * The MIT License (MIT)
 *
 * Copyright (c) 2019 Ha Thach (tinyusb.org)
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 *
 */

#include <limits.h>
#include <stdio.h>
#include <string.h>

#include "hardware/adc.h"
#include "hardware/gpio.h"
#include "hardware/irq.h"
#include "hardware/structs/ioqspi.h"
#include "hardware/sync.h"
#include "hardware/uart.h"
#include "pico/bootrom.h"
#include "pico/stdlib.h"
#include "pico/time.h"
#include "pico/types.h"

#include "tusb.h"

uint64_t get_current_time_us() { return to_us_since_boot(get_absolute_time()); }

bool __no_inline_not_in_flash_func(get_bootsel_button)() {
  const uint CS_PIN_INDEX = 1;

  // Must disable interrupts, as interrupt handlers may be in flash, and we
  // are about to temporarily disable flash access!
  uint32_t flags = save_and_disable_interrupts();

  // Set chip select to Hi-Z
  hw_write_masked(&ioqspi_hw->io[CS_PIN_INDEX].ctrl,
                  GPIO_OVERRIDE_LOW << IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_LSB,
                  IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_BITS);

  // Note we can't call into any sleep functions in flash right now
  for (volatile int i = 0; i < 1000; ++i)
    ;

  // The HI GPIO registers in SIO can observe and control the 6 QSPI pins.
  // Note the button pulls the pin *low* when pressed.
  bool button_state = !(sio_hw->gpio_hi_in & (1u << CS_PIN_INDEX));

  // Need to restore the state of chip select, else we are going to have a
  // bad time when we return to code in flash!
  hw_write_masked(&ioqspi_hw->io[CS_PIN_INDEX].ctrl,
                  GPIO_OVERRIDE_NORMAL << IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_LSB,
                  IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_BITS);

  restore_interrupts(flags);

  return button_state;
}

void set_led_on(bool on) { gpio_put(PICO_DEFAULT_LED_PIN, on); }

typedef struct TU_ATTR_PACKED {
  uint8_t keycodes[14]; /**< Key codes of the currently pressed keys. */
} keyboard_report_t;

keyboard_report_t report;

uint gpio_rows[] = {2,6,12,14,15};
uint gpio_cols[] = {0,4,9,7,13,11};

bool set_bit(bool newVal, uint hid_key, uint8_t ptr[14])
{
    uint elem;
    uint bit;
    if (hid_key >= HID_KEY_CONTROL_LEFT && hid_key <= HID_KEY_GUI_RIGHT)
    {
        bit = hid_key - HID_KEY_CONTROL_LEFT;
        elem = 0;
    }
    else if (hid_key >= HID_KEY_A && hid_key <= HID_KEY_F16)
    {
        bit = (hid_key - HID_KEY_A) % 8;
        elem = (hid_key - HID_KEY_A) / 8 + 1;
    }
    else
        return false;
    bool prevVal = !!(ptr[elem] & (1 << bit));
    if (newVal == prevVal)
        return false;
    if (newVal)
        ptr[elem] |= (1 << bit);
    else
        ptr[elem] &= ~(1 << bit);
    return true;
}

int main(void) {
  const uint LED_PIN = PICO_DEFAULT_LED_PIN;
  gpio_init(LED_PIN);
  gpio_set_dir(LED_PIN, GPIO_OUT);

  tusb_init();

  set_led_on(true);

  memset(report.keycodes, 0, sizeof(report.keycodes));

  for (int i = 0; i < 5; i++) {
      uint gpio = gpio_rows[i];
      gpio_init(gpio);
      gpio_set_dir(gpio, GPIO_OUT);
  }
  for (int i = 0; i < 6; i++) {
      uint gpio = gpio_cols[i];
      gpio_init(gpio);
      gpio_set_dir(gpio, GPIO_IN);
      gpio_pull_down(gpio);
  }

  const uint key_table[5][6] = {
      {HID_KEY_A, HID_KEY_B, HID_KEY_C, HID_KEY_D, HID_KEY_E, HID_KEY_CONTROL_LEFT},
      {HID_KEY_F, HID_KEY_G, HID_KEY_H, HID_KEY_I, HID_KEY_J, HID_KEY_ALT_LEFT},
      {HID_KEY_K, HID_KEY_L, HID_KEY_M, HID_KEY_N, HID_KEY_O, HID_KEY_SHIFT_LEFT},
      {HID_KEY_P, HID_KEY_Q, HID_KEY_R, HID_KEY_S, HID_KEY_T, HID_KEY_GUI_LEFT},
      {HID_KEY_U, HID_KEY_V, HID_KEY_W, HID_KEY_X, HID_KEY_NONE, HID_KEY_NONE},
  };

  uint8_t magic[14];
  memset(magic, 0, sizeof(magic));
  set_bit(true, key_table[0][0], magic);
  set_bit(true, key_table[3][0], magic);
  set_bit(true, key_table[0][5], magic);
  set_bit(true, key_table[3][5], magic);

  uint8_t debounce_table[5][6] = {
      {0, 0, 0, 0, 0, 0},
      {0, 0, 0, 0, 0, 0},
      {0, 0, 0, 0, 0, 0},
      {0, 0, 0, 0, 0, 0},
      {0, 0, 0, 0, 0, 0},
  };
  const uint8_t debounce_cycles = 3;

  uint64_t next_timepoint = get_current_time_us();
  bool sent = false;
  while (true) {
    do {
      tud_task();
    } while (get_current_time_us() < next_timepoint);
    next_timepoint = delayed_by_us(next_timepoint, 1000);

    if (get_bootsel_button())
      reset_usb_boot(0, 0);

    bool changed = false;
    for (uint row = 0; row < 5; ++row)
    {
        gpio_put(gpio_rows[row], true);
        sleep_us(1);
        for (uint col = 0; col < 6; ++col)
        {
            if (debounce_table[row][col] > 0)
                debounce_table[row][col]--;
            else
            {
                bool set = gpio_get(gpio_cols[col]);
                uint index = key_table[row][col];
                if (set_bit(set, index, report.keycodes))
                {
                    changed = true;
                    debounce_table[row][col] = debounce_cycles;
                }
            }
        }
        gpio_put(gpio_rows[row], false);
    }

    if (memcmp(magic, report.keycodes, sizeof(magic)) == 0)
      reset_usb_boot(0, 0);

    if (!tud_ready())
       continue;
    if (changed || !sent)
      sent = tud_hid_report(0, &report, sizeof(report));
  }
}

//--------------------------------------------------------------------+
// Device callbacks
//--------------------------------------------------------------------+

uint16_t tud_hid_get_report_cb(uint8_t itf, uint8_t report_id,
                               hid_report_type_t report_type, uint8_t *buffer,
                               uint16_t reqlen) {
  return 0;
}

void tud_hid_set_report_cb(uint8_t itf, uint8_t report_id,
                           hid_report_type_t report_type, uint8_t const *buffer,
                           uint16_t bufsize) {
}
