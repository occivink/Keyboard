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
#include <stdlib.h>
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
#include "pico/util/queue.h"

#include "tusb.h"

uint64_t get_current_time_us() { return to_us_since_boot(get_absolute_time()); }

bool __no_inline_not_in_flash_func(get_bootsel_button)() {
    const uint CS_PIN_INDEX = 1;

    // Must disable interrupts, as interrupt handlers may be in flash, and we
    // are about to temporarily disable flash access!
    uint32_t flags = save_and_disable_interrupts();

    // Set chip select to Hi-Z
    hw_write_masked(&ioqspi_hw->io[CS_PIN_INDEX].ctrl, GPIO_OVERRIDE_LOW << IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_LSB,
                    IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_BITS);

    // Note we can't call into any sleep functions in flash right now
    for (volatile int i = 0; i < 1000; ++i)
        ;

    // The HI GPIO registers in SIO can observe and control the 6 QSPI pins.
    // Note the button pulls the pin *low* when pressed.
    bool button_state = !(sio_hw->gpio_hi_in & (1u << CS_PIN_INDEX));

    // Need to restore the state of chip select, else we are going to have a
    // bad time when we return to code in flash!
    hw_write_masked(&ioqspi_hw->io[CS_PIN_INDEX].ctrl, GPIO_OVERRIDE_NORMAL << IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_LSB,
                    IO_QSPI_GPIO_QSPI_SS_CTRL_OEOVER_BITS);

    restore_interrupts(flags);

    return button_state;
}

void set_led_on(bool on) { gpio_put(PICO_DEFAULT_LED_PIN, on); }

// gpio_rows is defined left-to-right, and gpio_cols from top-to-bottom
#define IS_LEFT 0

#if IS_LEFT

const bool force_slave = true;
const uint gpio_rows[] = {2, 6, 12, 14, 15};
const uint gpio_cols[] = {11, 13, 7, 9, 4, 0};
#define UART uart0
#define UART_TX 16
#define UART_RX 17
#define LEFT_KEY_TABLE this_key_table
#define RIGHT_KEY_TABLE other_key_table

#else

const bool force_slave = false;
const uint gpio_rows[] = {2, 5, 9, 14, 10};
const uint gpio_cols[] = {1, 4, 18, 19, 16, 17};
#define UART uart0
#define UART_TX 12
#define UART_RX 13
#define LEFT_KEY_TABLE other_key_table
#define RIGHT_KEY_TABLE this_key_table

#endif

// clang-format off
#define K(K) HID_KEY_ ## K
const uint LEFT_KEY_TABLE[5][6] = {
    {K(GUI_LEFT)     , K(0)            , K(1)            , K(2)            , K(3)            , K(4)            },
    {K(ALT_LEFT)     , K(Q)            , K(W)            , K(E)            , K(R)            , K(T)            },
    {K(SHIFT_LEFT)   , K(A)            , K(S)            , K(D)            , K(F)            , K(G)            },
    {K(CONTROL_LEFT) , K(Z)            , K(X)            , K(C)            , K(V)            , K(B)            },
    {K(NONE)         , K(NONE)         , K(ARROW_LEFT)   , K(BACKSPACE)    , K(SPACE)        , K(TAB)          },
};
const uint RIGHT_KEY_TABLE[5][6] = {
    {K(5)            , K(6)            , K(7)            , K(8)            , K(9)            , K(CONTROL_RIGHT)},
    {K(Y)            , K(U)            , K(I)            , K(O)            , K(P)            , K(ALT_RIGHT)    },
    {K(H)            , K(J)            , K(K)            , K(L)            , K(SEMICOLON)    , K(SHIFT_RIGHT)  },
    {K(N)            , K(M)            , K(COMMA)        , K(PERIOD)       , K(SLASH)        , K(GUI_RIGHT)    },
    {K(ESCAPE)       , K(ENTER)        , K(DELETE)       , K(ARROW_RIGHT)  , K(NONE)         , K(NONE)         },
};
#undef K
// clang-format on

bool set_bit(bool newVal, uint hid_key, uint8_t report[14]) {
    uint elem;
    uint bit;
    if (hid_key >= HID_KEY_CONTROL_LEFT && hid_key <= HID_KEY_GUI_RIGHT) {
        bit = hid_key - HID_KEY_CONTROL_LEFT;
        elem = 0;
    } else if (hid_key >= HID_KEY_A && hid_key <= HID_KEY_F16) {
        bit = (hid_key - HID_KEY_A) % 8;
        elem = (hid_key - HID_KEY_A) / 8 + 1;
    } else
        return false;
    bool prevVal = !!(report[elem] & (1 << bit));
    if (newVal == prevVal)
        return false;
    if (newVal)
        report[elem] |= (1 << bit);
    else
        report[elem] &= ~(1 << bit);
    return true;
}

queue_t queue_other_half;
void on_uart_rx(void) {
    while (uart_is_readable(UART)) {
        uint8_t val;
        uart_read_blocking(UART, &val, 1);
        queue_try_add(&queue_other_half, &val);
    }
}

int main(void) {
    const uint LED_PIN = PICO_DEFAULT_LED_PIN;
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);

    queue_init(&queue_other_half, 1, 16);

    tusb_init();

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

    uart_init(UART, 115200);
    gpio_set_function(UART_TX, GPIO_FUNC_UART);
    gpio_set_function(UART_RX, GPIO_FUNC_UART);
    uart_set_hw_flow(UART, false, false);
    uart_set_format(UART, 8, 1, UART_PARITY_EVEN);
    uart_set_fifo_enabled(UART, false);

    irq_set_exclusive_handler(UART0_IRQ, on_uart_rx);
    irq_set_enabled(UART0_IRQ, true);
    uart_set_irq_enables(UART, true, false);

    const uint8_t debounce_cycles = 3;
    // the debounce table only applies to the current controller
    // the other half takes care of its own debouncing
    uint8_t debounce_table[5][6];
    // only used by the slave side
    bool state_table[5][6];

    for (int i = 0; i < 5; ++i)
        for (int j = 0; j < 6; ++j) {
            state_table[i][j] = false;
            debounce_table[i][j] = 0;
        }

    uint8_t report[14];
    memset(report, 0, sizeof(report));

    uint8_t magic[14];
    memset(magic, 0, sizeof(magic));
    set_bit(true, this_key_table[0][0], magic);
    set_bit(true, this_key_table[3][0], magic);
    set_bit(true, this_key_table[0][5], magic);
    set_bit(true, this_key_table[3][5], magic);

    uint64_t next_timepoint = get_current_time_us();
    bool sent = false;
    while (true) {
        do {
            tud_task();
        } while (get_current_time_us() < next_timepoint);
        next_timepoint = delayed_by_us(next_timepoint, 1000);

        if (get_bootsel_button())
            reset_usb_boot(0, 0);

        if (!force_slave && tud_mounted()) {
            // master side
            bool changed = false;

            // check values of local matrix
            for (uint8_t row = 0; row < 5; ++row) {
                gpio_put(gpio_rows[row], true);
                sleep_us(1);
                for (uint8_t col = 0; col < 6; ++col) {
                    if (debounce_table[row][col] > 0) {
                        debounce_table[row][col]--;
                    } else {
                        bool set = gpio_get(gpio_cols[col]);
                        uint hid_key = this_key_table[row][col];
                        if (set_bit(set, hid_key, report)) {
                            changed = true;
                            debounce_table[row][col] = debounce_cycles;
                        }
                    }
                }
                gpio_put(gpio_rows[row], false);
            }

            // handle values we received from the other matrix over UART
            uint8_t value;
            while (queue_try_remove(&queue_other_half, &value)) {
                bool set = value & (1 << 7);
                value &= ~(1 << 7);

                uint8_t col = value % 6;
                uint8_t row = value / 6;
                if (row < 5) {
                    uint hid_key = other_key_table[row][col];
                    if (set_bit(set, hid_key, report)) {
                        changed = true;
                    }
                }
            }

            if (memcmp(magic, report, sizeof(magic)) == 0)
                reset_usb_boot(0, 0);

            if (!tud_ready())
                continue;
            if (changed || !sent)
                sent = tud_hid_report(0, &report, sizeof(report));

        } else {

            // slave side
            uint8_t count = 0;
            for (uint8_t row = 0; row < 5; ++row) {
                gpio_put(gpio_rows[row], true);
                sleep_us(1);
                for (uint8_t col = 0; col < 6; ++col) {
                    if (debounce_table[row][col] > 0) {
                        debounce_table[row][col]--;
                    } else {
                        bool set = gpio_get(gpio_cols[col]);
                        if (set != state_table[row][col]) {
                            state_table[row][col] = set;
                            uint8_t value = count;
                            if (set)
                                value |= (1 << 7);
                            uart_write_blocking(UART, &value, 1);
                        }
                    }
                    count++;
                }
                gpio_put(gpio_rows[row], false);
            }
        }
    }
}

//--------------------------------------------------------------------+
// Device callbacks
//--------------------------------------------------------------------+

uint16_t tud_hid_get_report_cb(uint8_t itf, uint8_t report_id, hid_report_type_t report_type, uint8_t *buffer,
                               uint16_t reqlen) {
    return 0;
}

void tud_hid_set_report_cb(uint8_t itf, uint8_t report_id, hid_report_type_t report_type, uint8_t const *buffer,
                           uint16_t bufsize) {}
