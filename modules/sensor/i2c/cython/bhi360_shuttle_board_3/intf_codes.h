#ifndef INTF_CODES_H_
#define INTF_CODES_H_

#ifdef __cplusplus
extern "C" {
#endif

/*! success code */
#define INFT_SUCCESS                             0

/*! error code - failure */
#define INTF_E_FAILURE                           -1

/*! error code - IO error */
#define INTF_E_COMM_IO_ERROR                     -2

/*! error code - Init failure */
#define INTF_E_COMM_INIT_FAILED                  -3

/*! error code - failure to open device */
#define INTF_E_UNABLE_OPEN_DEVICE                -4

/*! error code - Device not found */
#define INTF_E_DEVICE_NOT_FOUND                  -5

/*! error code - failure to claim interface */
#define INTF_E_UNABLE_CLAIM_INTF                 -6

/*! error code - failure to allocate memory */
#define INTF_E_MEMORY_ALLOCATION                 -7

/*! error code - Feature not supported */
#define INTF_E_NOT_SUPPORTED                     -8

/*! error code - Null pointer */
#define INTF_E_NULL_PTR                          -9

/*! error code - Wrong response */
#define INTF_E_COMM_WRONG_RESPONSE               -10

/*! error code - Not configured */
#define INTF_E_SPI16BIT_NOT_CONFIGURED           -11

/*! error code - SPI invalid bus interface */
#define INTF_E_SPI_INVALID_BUS_INTF              -12

/*! error code - SPI instance configured already */
#define INTF_E_SPI_CONFIG_EXIST                  -13

/*! error code - SPI bus not enabled */
#define INTF_E_SPI_BUS_NOT_ENABLED               -14

/*! error code - SPI instance configuration failed */
#define INTF_E_SPI_CONFIG_FAILED                 -15

/*! error code - I2C invalid bus interface */
#define INTF_E_I2C_INVALID_BUS_INTF              -16

/*! error code - I2C bus not enabled */
#define INTF_E_I2C_BUS_NOT_ENABLED               -17

/*! error code - I2C instance configuration failed */
#define INTF_E_I2C_CONFIG_FAILED                 -18

/*! error code - I2C instance configured already */
#define INTF_E_I2C_CONFIG_EXIST                  -19

/*! error code - Timer initialization failed */
#define INTF_E_TIMER_INIT_FAILED                 -20

/*! error code - Invalid timer instance */
#define INTF_E_TIMER_INVALID_INSTANCE            -21

/*! error code - Invalid timer instance */
#define INTF_E_TIMER_CC_CHANNEL_NOT_AVAILABLE    -22

/*! error code - EEPROM reset failed */
#define INTF_E_EEPROM_RESET_FAILED               -23

/*! error code - EEPROM read failed */
#define INTF_E_EEPROM_READ_FAILED                -24

/*! error code - Initialization failed */
#define INTF_E_INIT_FAILED                       -25

/*! error code - Streaming not configure */
#define INTF_E_STREAM_NOT_CONFIGURED             -26

/*! error code - Streaming invalid block size */
#define INTF_E_STREAM_INVALID_BLOCK_SIZE         -27

/*! error code - Streaming sensor already configured */
#define INTF_E_STREAM_SENSOR_ALREADY_CONFIGURED  -28

/*! error code - Streaming sensor config memory full */
#define INTF_E_STREAM_CONFIG_MEMORY_FULL         -29

/*! error code - Invalid payload length */
#define INTF_E_INVALID_PAYLOAD_LEN               -30

/*! error code - channel allocation failed */
#define INTF_E_CHANNEL_ALLOCATION_FAILED         -31

/*! error code - channel de-allocation failed */
#define INTF_E_CHANNEL_DEALLOCATION_FAILED       -32

/*! error code - channel assignment failed */
#define INTF_E_CHANNEL_ASSIGN_FAILED             -33

/*! error code - channel enable failed */
#define INTF_E_CHANNEL_ENABLE_FAILED             -34

/*! error code - channel disable failed */
#define INTF_E_CHANNEL_DISABLE_FAILED            -35

/*! error code - GPIO invalid pin number */
#define INTF_E_INVALID_PIN_NUMBER                -36

/*! error code - GPIO invalid pin number */
#define INTF_E_MAX_SENSOR_COUNT_REACHED          -37

/*! error code - EEPROM write failed */
#define INTF_E_EEPROM_WRITE_FAILED               -38

/*! error code - Invalid EEPROM write length */
#define INTF_E_INVALID_EEPROM_RW_LENGTH          -39

/*! error code - Invalid serial com config */
#define INTF_E_SCOM_INVALID_CONFIG               -40

/*! error code - Invalid BLE config */
#define INTF_E_BLE_INVALID_CONFIG                -41

/*! error code - Serial com port in use */
#define INTF_E_SCOM_PORT_IN_USE                  -42

/*! error code - UART initialization failed  */
#define INTF_E_UART_INIT_FAILED                  -43

/*! error code - UART write operation failed  */
#define INTF_E_UART_WRITE_FAILED                 -44

/*! error code - UART instance check failed  */
#define INTF_E_UART_INSTANCE_NOT_SUPPORT         -45

/*! error code - BLE Adaptor not found  */
#define INTF_E_BLE_ADAPTOR_NOT_FOUND             -46

/*! error code - BLE not enabled  */
#define INTF_E_BLE_ADAPTER_BLUETOOTH_NOT_ENABLED     -47

/*! error code - BLE peripheral not found  */
#define INTF_E_BLE_PERIPHERAL_NOT_FOUND          -48

/*! error code - BLE library not loaded  */
#define INTF_E_BLE_LIBRARY_NOT_LOADED            -49

/*! error code - APP board BLE not found  */
#define INTF_E_BLE_APP_BOARD_NOT_FOUND           -50

/*! error code - BLE COMM failure  */
#define INTF_E_BLE_COMM_FAILED                   -51

/*! error code - incompatible firmware for the selected comm type */
#define INTF_E_INCOMPATIBLE_FIRMWARE             -52

/*! error code - read timeout */
#define INTF_E_READ_TIMEOUT                      -53

/*! error code - VDD configuration failed */
#define INTF_E_VDD_CONFIG_FAILED                 -54

/*! error code - VDDIO configuration failed */
#define INTF_E_VDDIO_CONFIG_FAILED               -55

/*! error code - Serial COMM failure  */
#define INTF_E_SERIAL_COMM_FAILED				   -56

/*! error code - Serial COMM failure  */
#define INTF_E_INTERFACE_FAILED				   -57

/*! error code - decoder failed  */
#define INTF_E_DECODER_FAILED                	   -58

/*! error code - encoder failed  */
#define INTF_E_ENCODER_FAILED					   -59

/*! error code - pthread failed  */
#define INTF_E_PTHREAD_FAILED					   -60

/*! error code - Initialization failed */
#define INTF_E_DEINIT_FAILED                     -61

/*! error code - Streaming not started */
#define INTF_E_STREAMING_INIT_FAILURE            -62

/*! error code - Invalid param */
#define INTF_E_INVALID_PARAM                     -63

/*! Variable to hold the number of error codes */
#define NUM_ERROR_CODES                             64

#ifdef __cplusplus
}
#endif

#endif