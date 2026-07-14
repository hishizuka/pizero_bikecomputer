/**
 * Copyright (c) 2025 Bosch Sensortec GmbH. All rights reserved.
 *
 * BSD-3-Clause
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are met:
 *
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 *
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * 3. Neither the name of the copyright holder nor the names of its
 *    contributors may be used to endorse or promote products derived from
 *    this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
 * FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
 * COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
 * INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
 * (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
 * SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION)
 * HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT,
 * STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING
 * IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
 * POSSIBILITY OF SUCH DAMAGE.
 *
 * @file    coines.h
 * @brief   This file contains COINES_SDK layer function prototypes, variable declarations and Macro definitions
 *
 * Source: https://github.com/boschsensortec/COINES_SDK/blob/main/coines-api/coines.h
 *
 */

#ifndef COINES_H_
#define COINES_H_

#ifdef __cplusplus
extern "C" {
#endif


/*! COINES_SDK success code */
#define COINES_SUCCESS                             0

/*! COINES_SDK error code - failure */
#define COINES_E_FAILURE                           -1

/*! COINES_SDK error code - IO error */
#define COINES_E_COMM_IO_ERROR                     -2

/*! COINES_SDK error code - Init failure */
#define COINES_E_COMM_INIT_FAILED                  -3

/*! COINES_SDK error code - failure to open device */
#define COINES_E_UNABLE_OPEN_DEVICE                -4

/*! COINES_SDK error code - Device not found */
#define COINES_E_DEVICE_NOT_FOUND                  -5

/*! COINES_SDK error code - failure to claim interface */
#define COINES_E_UNABLE_CLAIM_INTF                 -6

/*! COINES_SDK error code - failure to allocate memory */
#define COINES_E_MEMORY_ALLOCATION                 -7

/*! COINES_SDK error code - Feature not supported */
#define COINES_E_NOT_SUPPORTED                     -8

/*! COINES_SDK error code - Null pointer */
#define COINES_E_NULL_PTR                          -9

/*! COINES_SDK error code - Wrong response */
#define COINES_E_COMM_WRONG_RESPONSE               -10

/*! COINES_SDK error code - Not configured */
#define COINES_E_SPI16BIT_NOT_CONFIGURED           -11

/*! COINES_SDK error code - SPI invalid bus interface */
#define COINES_E_SPI_INVALID_BUS_INTF              -12

/*! COINES_SDK error code - SPI instance configured already */
#define COINES_E_SPI_CONFIG_EXIST                  -13

/*! COINES_SDK error code - SPI bus not enabled */
#define COINES_E_SPI_BUS_NOT_ENABLED               -14

/*! COINES_SDK error code - SPI instance configuration failed */
#define COINES_E_SPI_CONFIG_FAILED                 -15

/*! COINES_SDK error code - I2C invalid bus interface */
#define COINES_E_I2C_INVALID_BUS_INTF              -16

/*! COINES_SDK error code - I2C bus not enabled */
#define COINES_E_I2C_BUS_NOT_ENABLED               -17

/*! COINES_SDK error code - I2C instance configuration failed */
#define COINES_E_I2C_CONFIG_FAILED                 -18

/*! COINES_SDK error code - I2C instance configured already */
#define COINES_E_I2C_CONFIG_EXIST                  -19

/*! COINES_SDK error code - Timer initialization failed */
#define COINES_E_TIMER_INIT_FAILED                 -20

/*! COINES_SDK error code - Invalid timer instance */
#define COINES_E_TIMER_INVALID_INSTANCE            -21

/*! COINES_SDK error code - Invalid timer instance */
#define COINES_E_TIMER_CC_CHANNEL_NOT_AVAILABLE    -22

/*! COINES_SDK error code - EEPROM reset failed */
#define COINES_E_EEPROM_RESET_FAILED               -23

/*! COINES_SDK error code - EEPROM read failed */
#define COINES_E_EEPROM_READ_FAILED                -24

/*! COINES_SDK error code - Initialization failed */
#define COINES_E_INIT_FAILED                       -25

/*! COINES_SDK error code - Streaming not configure */
#define COINES_E_STREAM_NOT_CONFIGURED             -26

/*! COINES_SDK error code - Streaming invalid block size */
#define COINES_E_STREAM_INVALID_BLOCK_SIZE         -27

/*! COINES_SDK error code - Streaming sensor already configured */
#define COINES_E_STREAM_SENSOR_ALREADY_CONFIGURED  -28

/*! COINES_SDK error code - Streaming sensor config memory full */
#define COINES_E_STREAM_CONFIG_MEMORY_FULL         -29

/*! COINES_SDK error code - Invalid payload length */
#define COINES_E_INVALID_PAYLOAD_LEN               -30

/*! COINES_SDK error code - channel allocation failed */
#define COINES_E_CHANNEL_ALLOCATION_FAILED         -31

/*! COINES_SDK error code - channel de-allocation failed */
#define COINES_E_CHANNEL_DEALLOCATION_FAILED       -32

/*! COINES_SDK error code - channel assignment failed */
#define COINES_E_CHANNEL_ASSIGN_FAILED             -33

/*! COINES_SDK error code - channel enable failed */
#define COINES_E_CHANNEL_ENABLE_FAILED             -34

/*! COINES_SDK error code - channel disable failed */
#define COINES_E_CHANNEL_DISABLE_FAILED            -35

/*! COINES_SDK error code - GPIO invalid pin number */
#define COINES_E_INVALID_PIN_NUMBER                -36

/*! COINES_SDK error code - GPIO invalid pin number */
#define COINES_E_MAX_SENSOR_COUNT_REACHED          -37

/*! COINES_SDK error code - EEPROM write failed */
#define COINES_E_EEPROM_WRITE_FAILED               -38

/*! COINES_SDK error code - Invalid EEPROM write length */
#define COINES_E_INVALID_EEPROM_RW_LENGTH          -39

/*! COINES_SDK error code - Invalid serial com config */
#define COINES_E_SCOM_INVALID_CONFIG               -40

/*! COINES_SDK error code - Invalid BLE config */
#define COINES_E_BLE_INVALID_CONFIG                -41

/*! COINES_SDK error code - Serial com port in use */
#define COINES_E_SCOM_PORT_IN_USE                  -42

/*! COINES_SDK error code - UART initialization failed  */
#define COINES_E_UART_INIT_FAILED                  -43

/*! COINES_SDK error code - UART write operation failed  */
#define COINES_E_UART_WRITE_FAILED                 -44

/*! COINES_SDK error code - UART instance check failed  */
#define COINES_E_UART_INSTANCE_NOT_SUPPORT         -45

/*! coines error code - BLE Adaptor not found  */
#define COINES_E_BLE_ADAPTOR_NOT_FOUND             -46

/*! coines error code - BLE not enabled  */
#define COINES_E_BLE_ADAPTER_BLUETOOTH_NOT_ENABLED     -47

/*! coines error code - BLE peripheral not found  */
#define COINES_E_BLE_PERIPHERAL_NOT_FOUND          -48

/*! coines error code - BLE library not loaded  */
#define COINES_E_BLE_LIBRARY_NOT_LOADED            -49

/*! coines error code - APP board BLE not found  */
#define COINES_E_BLE_APP_BOARD_NOT_FOUND           -50

/*! coines error code - BLE COMM failure  */
#define COINES_E_BLE_COMM_FAILED                   -51

/*! coines error code - incompatible firmware for the selected comm type */
#define COINES_E_INCOMPATIBLE_FIRMWARE             -52

/*! coines error code - read timeout */
#define COINES_E_READ_TIMEOUT                      -53

/*! COINES_SDK error code - VDD configuration failed */
#define COINES_E_VDD_CONFIG_FAILED                 -54

/*! COINES_SDK error code - VDDIO configuration failed */
#define COINES_E_VDDIO_CONFIG_FAILED               -55

/*! coines error code - Serial COMM failure  */
#define COINES_E_SERIAL_COMM_FAILED				   -56

/*! coines error code - Serial COMM failure  */
#define COINES_E_INTERFACE_FAILED				   -57

/*! coines error code - decoder failed  */
#define COINES_E_DECODER_FAILED                	   -58

/*! coines error code - encoder failed  */
#define COINES_E_ENCODER_FAILED					   -59

/*! coines error code - pthread failed  */
#define COINES_E_PTHREAD_FAILED					   -60

/*! COINES_SDK error code - Initialization failed */
#define COINES_E_DEINIT_FAILED                     -61

/*! COINES_SDK error code - Streaming not started */
#define COINES_E_STREAMING_INIT_FAILURE            -62

/*! COINES_SDK error code - Invalid param */
#define COINES_E_INVALID_PARAM                     -63

/*! Variable to hold the number of error codes */
#define NUM_ERROR_CODES                             64


#ifdef __cplusplus
}
#endif

#endif
