from gpiozero import InputDevice
import time
import spidev
import pygame

# LoRa registers
REG_FIFO                   = 0x00
REG_FIFO_ADDR_PTR          = 0x0D 
REG_FIFO_TX_BASE_AD        = 0x0E
REG_FIFO_RX_BASE_AD        = 0x0F
REG_RX_NB_BYTES            = 0x13
REG_OPMODE                 = 0x01
REG_FIFO_RX_CURRENT_ADDR   = 0x10
REG_IRQ_FLAGS              = 0x12
REG_PACKET_SNR				= 0x19
REG_PACKET_RSSI				= 0x1A
REG_CURRENT_RSSI			= 0x1B
REG_DIO_MAPPING_1          = 0x40
REG_DIO_MAPPING_2          = 0x41
REG_MODEM_CONFIG           = 0x1D
REG_MODEM_CONFIG2          = 0x1E
REG_MODEM_CONFIG3          = 0x26
REG_PAYLOAD_LENGTH         = 0x22
REG_IRQ_FLAGS_MASK         = 0x11
REG_HOP_PERIOD             = 0x24
REG_FREQ_ERROR				= 0x28
REG_DETECT_OPT				= 0x31
REG_DETECTION_THRESHOLD	= 0x37

# MODES
RF98_MODE_RX_CONTINUOUS    = 0x85
RF98_MODE_TX               = 0x83
RF98_MODE_SLEEP            = 0x80
RF98_MODE_STANDBY          = 0x81

# Modem Config 1
EXPLICIT_MODE              = 0x00
IMPLICIT_MODE              = 0x01

ERROR_CODING_4_5           = 0x02
ERROR_CODING_4_6           = 0x04
ERROR_CODING_4_7           = 0x06
ERROR_CODING_4_8           = 0x08

BANDWIDTH_7K8              = 0x00
BANDWIDTH_10K4             = 0x10
BANDWIDTH_15K6             = 0x20
BANDWIDTH_20K8             = 0x30
BANDWIDTH_31K25            = 0x40
BANDWIDTH_41K7             = 0x50
BANDWIDTH_62K5             = 0x60
BANDWIDTH_125K             = 0x70
BANDWIDTH_250K             = 0x80
BANDWIDTH_500K             = 0x90

# Modem Config 2

SPREADING_6                = 0x60
SPREADING_7                = 0x70
SPREADING_8                = 0x80
SPREADING_9                = 0x90
SPREADING_10               = 0xA0
SPREADING_11               = 0xB0
SPREADING_12               = 0xC0

CRC_OFF                    = 0x00
CRC_ON                     = 0x04

# POWER AMPLIFIER CONFIG
REG_PA_CONFIG              = 0x09
PA_MAX_BOOST               = 0x8F
PA_LOW_BOOST               = 0x81
PA_MED_BOOST               = 0x8A
PA_MAX_UK                  = 0x88
PA_OFF_BOOST               = 0x00
RFO_MIN                    = 0x00

# LOW NOISE AMPLIFIER
REG_LNA                    = 0x0C
LNA_MAX_GAIN               = 0x23  # 0010 0011
LNA_OFF_GAIN               = 0x00
LNA_LOW_GAIN               = 0xC0  # 1100 0000


# Joystick channels and configuration
XChannel = 3
YChannel = 4
XChannelMultipler = -1
YChannelMultipler =  1

currentMode = -1

def WriteRegister(register, value):
	spi.xfer([register | 0x80, value])
	
def ReadRegister(register):
	data = [register & 0x7F, 0]
	result = spi.xfer(data)
	return result[1]
	

def SetMode(newMode):
	global currentMode
	
	if newMode != currentMode:
		if newMode == RF98_MODE_TX:
			# TURN LNA OFF FOR TRANSMIT
			WriteRegister(REG_LNA, LNA_OFF_GAIN)
			
			# Set 10mW
			WriteRegister(REG_PA_CONFIG, PA_MAX_UK)
		elif newMode == RF98_MODE_RX_CONTINUOUS:
			# PA Off
			WriteRegister(REG_PA_CONFIG, PA_OFF_BOOST)
			
			# Max LNA Gain
			WriteRegister(REG_LNA, LNA_MAX_GAIN)
	
		WriteRegister(REG_OPMODE, newMode)
		currentMode = newMode
	
def SetLoRaFrequency(Frequency):
	SetMode(RF98_MODE_STANDBY)
	SetMode(RF98_MODE_SLEEP)
	WriteRegister(REG_OPMODE, 0x80);
	SetMode(RF98_MODE_STANDBY)
	
	FrequencyValue = int((Frequency * 7110656) / 434)

	WriteRegister(0x06, (FrequencyValue >> 16) & 0xFF)
	WriteRegister(0x07, (FrequencyValue >> 8) & 0xFF)
	WriteRegister(0x08, FrequencyValue & 0xFF)

def SetLoRaParameters(ImplicitOrExplicit, ErrorCoding, Bandwidth, SpreadingFactor, LowDataRateOptimize):
	global PayloadLength
	
	WriteRegister(REG_MODEM_CONFIG, ImplicitOrExplicit | ErrorCoding | Bandwidth)
	WriteRegister(REG_MODEM_CONFIG2, SpreadingFactor | CRC_ON)
	WriteRegister(REG_MODEM_CONFIG3, 0x04 | (0x08 if LowDataRateOptimize else 0))
	WriteRegister(REG_DETECT_OPT, (ReadRegister(REG_DETECT_OPT) & 0xF8) | (0x05 if (SpreadingFactor == SPREADING_6) else 0x03))
	WriteRegister(REG_DETECTION_THRESHOLD, 0x0C if (SpreadingFactor == SPREADING_6) else 0x0A)

	PayloadLength = 255 if (ImplicitOrExplicit == IMPLICIT_MODE) else 0

	WriteRegister(REG_PAYLOAD_LENGTH, PayloadLength)
	WriteRegister(REG_RX_NB_BYTES, PayloadLength)

def SetStandardLoRaParameters(Mode):
	if Mode == 0:
		SetLoRaParameters(EXPLICIT_MODE, ERROR_CODING_4_8, BANDWIDTH_20K8, SPREADING_11, True)
	elif Mode == 1:
		SetLoRaParameters(IMPLICIT_MODE, ERROR_CODING_4_5, BANDWIDTH_20K8, SPREADING_6, False)
	elif Mode == 2:
		SetLoRaParameters(EXPLICIT_MODE, ERROR_CODING_4_8, BANDWIDTH_62K5, SPREADING_8, False)
	elif Mode == 7:
		SetLoRaParameters(EXPLICIT_MODE, ERROR_CODING_4_5, BANDWIDTH_20K8, SPREADING_7, False)
	
def SendMessage(text):
	global PayloadLength
	
	packet = text.encode()
	
	SetMode(RF98_MODE_STANDBY)

	# map DIO0 to TxDone
	WriteRegister(REG_DIO_MAPPING_1, 0x40)

	WriteRegister(REG_FIFO_TX_BASE_AD, 0x00)
	WriteRegister(REG_FIFO_ADDR_PTR, 0x00)

	data = [REG_FIFO | 0x80] + list(packet) + [0]
	spi.xfer(data)
	
	WriteRegister(REG_PAYLOAD_LENGTH, PayloadLength if PayloadLength else len(packet))

	SetMode(RF98_MODE_TX);
	
	while not DIO0.is_active:			
		time.sleep(0.01)
		
	# Reset TxSent thus resetting DIO0
	WriteRegister(REG_IRQ_FLAGS, 0x08); 
	
	
# Init pygame
pygame.init()
pygame.joystick.init()
print ("There are ", pygame.joystick.get_count(), "joysticks")
joystick = pygame.joystick.Joystick(0)
joystick.init()
if joystick.get_init():
	print ("Joystick init OK")
	print ("Joystick has " + str(joystick.get_numbuttons()) + " buttons")
	print ("Joystick has " + str(joystick.get_numhats()) + " hats")
	print ("Joystick has " + str(joystick.get_numaxes()) + " axes")
	
# Init SPI and LoRa
spi = spidev.SpiDev()
spi.open(0, 0)			## Channel 0
spi.max_speed_hz = 976000
currentMode = -1
DIO0 = InputDevice(25)
WriteRegister(REG_DIO_MAPPING_2, 0x00)
SetLoRaFrequency(434.450)
SetStandardLoRaParameters(7)
X = 0
Y = 0

print ('Joystick RTLS1 Controller - ' + joystick.get_name())
while True:
	events = pygame.event.get()
	for event in events:
		if event.type == pygame.JOYBUTTONDOWN:
			if event.button == 0:
				Y = 45
			elif event.button == 1:
				X = 45
			elif event.button == 2:
				Y = -45
			elif event.button == 3:
				X = -45
			else:
				X = 0
				Y = 0
		# elif event.type == pygame.JOYBUTTONUP:
			# print ("Key up")
		elif event.type == pygame.JOYAXISMOTION:
			# A joystick has been moved, read axis positions (-1 to +1)
			if event.axis == XChannel:
				X = int(event.value * 45)
			elif event.axis == YChannel:
				Y = -int(event.value * 45)
	message = ">" + str(X) + "," + str(Y) + ",0"
	print(message)
	SendMessage(message)
	# time.sleep(0.1)
	