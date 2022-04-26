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
  uint8_t modifier;    /**< Keyboard modifier (KEYBOARD_MODIFIER_* masks). */
  uint8_t keycode[13]; /**< Key codes of the currently pressed keys. */
} keyboard_report_t;

bool usb_mounted = false;

keyboard_report_t report;
keyboard_report_t old_report;

uint gpio_rows[] = {2,6,12,14,15};
uint gpio_cols[] = {0,3,9,7,13,11};

int main(void) {
  const uint LED_PIN = PICO_DEFAULT_LED_PIN;
  gpio_init(LED_PIN);
  gpio_set_dir(LED_PIN, GPIO_OUT);

  tusb_init();

  uint64_t init_time = get_current_time_us();
  const uint64_t check_usb_duration = 1000 * 1000; // 1s

  set_led_on(true);

  report.modifier = 0;
  memset(report.keycode, 0, sizeof(report.keycode));
  memcpy(&old_report, &report, sizeof(report));

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


  absolute_time_t next_timepoint = get_absolute_time();
  while (true) {
    next_timepoint = delayed_by_us(next_timepoint, 1000);
    do {
      tud_task();
    } while (get_current_time_us() < next_timepoint);

    if (get_bootsel_button()) {
      reset_usb_boot(0, 0);
    }

    uint key_table[5][6] = {
        {HID_KEY_A, HID_KEY_B, HID_KEY_C, HID_KEY_D, HID_KEY_E, HID_KEY_1},
        {HID_KEY_F, HID_KEY_G, HID_KEY_H, HID_KEY_I, HID_KEY_J, HID_KEY_2},
        {HID_KEY_K, HID_KEY_L, HID_KEY_M, HID_KEY_N, HID_KEY_O, HID_KEY_3},
        {HID_KEY_P, HID_KEY_Q, HID_KEY_R, HID_KEY_S, HID_KEY_T, HID_KEY_4},
        {HID_KEY_U, HID_KEY_V, HID_KEY_W, HID_KEY_X, HID_KEY_Y, HID_KEY_5},
    };

    bool magic = true;
    for (uint row = 0; row < 5; ++row)
    {
        gpio_put(gpio_rows[row], true);
        sleep_us(1);
        for (uint col = 0; col < 6; ++col)
        {
            uint key = key_table[row][col];
            uint num = key - HID_KEY_A;
            uint elem = num / 8;
            uint bit = num % 8;
            bool set = gpio_get(gpio_cols[col]);
            if (set)
                report.keycode[elem] |= (1 << bit);
            else
                report.keycode[elem] &= ~(1 << bit);

            if (magic)
            {
                if ((col == 0 || col == 5) && (row == 0 || row == 3))
                    magic = set;
                else
                    magic = !set;
            }
        }
        gpio_put(gpio_rows[row], false);
        sleep_us(1);
    }

    if (magic)
      reset_usb_boot(0, 0);

    if (!tud_ready())
       continue;
    if (memcmp(&old_report, &report, sizeof(report)) == 0)
      continue;
    if (tud_hid_report(0, &report, sizeof(report)))
      memcpy(&old_report, &report, sizeof(report));
  }
}

//--------------------------------------------------------------------+
// Device callbacks
//--------------------------------------------------------------------+

// Invoked when device is mounted
void tud_mount_cb(void) { usb_mounted = true; }

// Invoked when device is unmounted
void tud_umount_cb(void) { usb_mounted = false; }

void tud_suspend_cb(bool remote_wakeup_en) {}

void tud_resume_cb(void) {}

uint16_t tud_hid_get_report_cb(uint8_t itf, uint8_t report_id,
                               hid_report_type_t report_type, uint8_t *buffer,
                               uint16_t reqlen) {
  // useless or wtf?
  return 0;
}

void tud_hid_set_report_cb(uint8_t itf, uint8_t report_id,
                           hid_report_type_t report_type, uint8_t const *buffer,
                           uint16_t bufsize) {
  // useless or wtf?
}
