#include <REG.h>
#include <wit_c_sdk.h>

/*
Test on MEGA 2560. use HW-97 module connect WT901C485 sensor
wiring:
  MEGA-2560            HW-97            WT901C485
   5V/3.3V  <--------------------------->  VCC
   5V/3.3V  <----->     VCC
     GND    <--------------------------->  GND2
                        GND   <----->      GND1  
   GPIO_21  <----->  DE and RE
     TX1    <----->     RO     
     RX1    <----->     DI
                         A    <----->    A
                         B    <----->    B
                        GND   <----->   GND
*/

#define ACC_UPDATE		0x01
#define GYRO_UPDATE		0x02
#define ANGLE_UPDATE	0x04
#define VEL_UPDATE		0x08
#define TEMP_UPDATE   0x10
#define DIS_UPDATE    0x20
#define HZ_UPDATE     0x40
#define READ_UPDATE		0x80
static volatile char s_cDataUpdate = 0, s_cCmd = 0xff;

static void CmdProcess(void);
static void RS485_IO_Init(void);
static void AutoScanSensor(void);
static void SensorUartSend(uint8_t *p_data, uint32_t uiSize);
static void CopeSensorData(uint32_t uiReg, uint32_t uiRegNum);
static void Delayms(uint16_t ucMs);
void GetData(float fAngle[3],short sVel[3],short sDis[3],short sHz[3],float fTemp);
void GetTime(void);

const uint32_t c_uiBaud[7] = { 0, 4800, 9600, 19200, 38400, 57600, 115200};

void setup() {
  // put your setup code here, to run once:
	Serial.begin(115200);
	RS485_IO_Init();
	WitInit(WIT_PROTOCOL_MODBUS, 0x50);
	WitSerialWriteRegister(SensorUartSend);
	WitRegisterCallBack(CopeSensorData);
  WitDelayMsRegister(Delayms);
	Serial.print("\r\n********************** wit-motion modbus example  ************************\r\n");
	AutoScanSensor();
}
struct STime
{
  unsigned char ucYear;
  unsigned char ucMonth;
  unsigned char ucDay;
  unsigned char ucHour;
  unsigned char ucMinute;
  unsigned char ucSecond;
  unsigned short usMs;
} stcTime;
int i;
float fAngle[3],ftemp;
short sVel[3],sDis[3],sHz[3];
void loop() {
	WitReadReg(YYMM, 23);
	delay(500);
    while (Serial1.available())
    {
      WitSerialDataIn(Serial1.read());
    }
    while (Serial.available()) 
    {
      CopeCmdData(Serial.read());
    }
		CmdProcess();
		if(s_cDataUpdate)
		{
      GetData(fAngle,sVel,sDis,sHz,ftemp);
      //GetTime();
      
			if(s_cDataUpdate & ANGLE_UPDATE)
			{
				Serial.print("angle:");
				Serial.print(fAngle[0], 3);
				Serial.print(" ");
				Serial.print(fAngle[1], 3);
				Serial.print(" ");
				Serial.print(fAngle[2], 3);
				Serial.print("\r\n");
				s_cDataUpdate &= ~ANGLE_UPDATE;
			}
     if(s_cDataUpdate & VEL_UPDATE)
     {
        Serial.print("vel:");
        Serial.print(sVel[0], 3);
        Serial.print(" mm/S ");
        Serial.print(sVel[1], 3);
        Serial.print(" mm/S ");
        Serial.print(sVel[2], 3);
        Serial.print(" mm/S\r\n");
        s_cDataUpdate &= ~VEL_UPDATE;
      }
      if(s_cDataUpdate & DIS_UPDATE)
      {
        Serial.print("dis:");
        Serial.print(sDis[0], 3);
        Serial.print(" um ");
        Serial.print(sDis[1], 3);
        Serial.print(" um ");
        Serial.print(sDis[2], 3);
        Serial.print(" um\r\n");
        s_cDataUpdate &= ~DIS_UPDATE;
      }
      if(s_cDataUpdate & HZ_UPDATE)
      {
        Serial.print("hz:");
        Serial.print(sHz[0], 3);
        Serial.print(" Hz ");
        Serial.print(sHz[1], 3);
        Serial.print(" Hz ");
        Serial.print(sHz[2], 3);
        Serial.print(" Hz\r\n");
        s_cDataUpdate &= ~HZ_UPDATE;
      }
     if(s_cDataUpdate & TEMP_UPDATE)
     {
        Serial.print("temp:");
        Serial.print(ftemp, 1);
        Serial.print("\r\n");
        s_cDataUpdate &= ~TEMP_UPDATE;
      }
      s_cDataUpdate = 0;
		}
}

void GetTime(void)
{
  stcTime.ucYear = (sReg[YYMM] >> 8) & 0xff;
  stcTime.ucMonth = sReg[YYMM] & 0xff;
  stcTime.ucDay = (sReg[DDHH] >> 8) & 0xff;
  stcTime.ucHour = sReg[DDHH] & 0xff;
  stcTime.ucMinute = (sReg[MMSS] >> 8) & 0xff;
  stcTime.ucSecond = sReg[MMSS] & 0xff;
  stcTime.usMs  = sReg[MS];

  Serial.print("Time:");
  Serial.print(stcTime.ucYear, 1);
  Serial.print(":");
  Serial.print(stcTime.ucMonth, 1);
  Serial.print(":");
  Serial.print(stcTime.ucDay, 1);
  Serial.print(":");
  Serial.print(stcTime.ucHour, 1);
  Serial.print(":");
  Serial.print(stcTime.ucMinute, 1);
  Serial.print(":");
  Serial.print(stcTime.ucSecond, 1);
  Serial.print(".");
  Serial.print(stcTime.usMs, 1);
  Serial.print("\r\n");
}
void GetData(float fAngle[3],short sVel[3],short sDis[3],short sHz[3],float fTemp)
{
      for(i = 0; i < 3; i++)
      {
        fAngle[i] = sReg[ADX+i] / 32768.0f * 180.0f;
        sVel[i] = sReg[VX+i];
        sDis[i] = sReg[DX+i];
        sHz[i] = sReg[HZX+i];
      }
      ftemp = sReg[TEMP] / 100.0f;
}

void CopeCmdData(unsigned char ucData)
{
	static unsigned char s_ucData[50], s_ucRxCnt = 0;
	
	s_ucData[s_ucRxCnt++] = ucData;
	if(s_ucRxCnt<3)return;										//Less than three data returned
	if(s_ucRxCnt >= 50) s_ucRxCnt = 0;
	if(s_ucRxCnt >= 3)
	{
		if((s_ucData[1] == '\r') && (s_ucData[2] == '\n'))
		{
			s_cCmd = s_ucData[0];
			memset(s_ucData,0,50);
			s_ucRxCnt = 0;
		}
		else 
		{
			s_ucData[0] = s_ucData[1];
			s_ucData[1] = s_ucData[2];
			s_ucRxCnt = 2;
			
		}
	}
}
static void ShowHelp(void)
{
	Serial.print("\r\n************************	 WIT_SDK_DEMO	************************");
	Serial.print("\r\n************************          HELP           ************************\r\n");
	Serial.print("UART SEND:a\\r\\n   Acceleration calibration.\r\n");
	Serial.print("UART SEND:m\\r\\n   Magnetic field calibration,After calibration send:   e\\r\\n   to indicate the end\r\n");
	Serial.print("UART SEND:U\\r\\n   Bandwidth increase.\r\n");
	Serial.print("UART SEND:u\\r\\n   Bandwidth reduction.\r\n");
	Serial.print("UART SEND:B\\r\\n   Baud rate increased to 115200.\r\n");
	Serial.print("UART SEND:b\\r\\n   Baud rate reduction to 9600.\r\n");
	Serial.print("UART SEND:h\\r\\n   help.\r\n");
	Serial.print("******************************************************************************\r\n");
}

static void CmdProcess(void)
{
	switch(s_cCmd)
	{
		case 'a':	if(WitStartAccCali() != WIT_HAL_OK) Serial.print("\r\nSet AccCali Error\r\n");
			break;
		case 'm':	if(WitStartMagCali() != WIT_HAL_OK) Serial.print("\r\nSet MagCali Error\r\n");
			break;
		case 'e':	if(WitStopMagCali() != WIT_HAL_OK) Serial.print("\r\nSet MagCali Error\r\n");
			break;
		case 'u':	if(WitSetBandwidth(BANDWIDTH_5HZ) != WIT_HAL_OK) Serial.print("\r\nSet Bandwidth Error\r\n");
			break;
		case 'U':	if(WitSetBandwidth(BANDWIDTH_256HZ) != WIT_HAL_OK) Serial.print("\r\nSet Bandwidth Error\r\n");
			break;
		case 'B':	if(WitSetUartBaud(WIT_BAUD_115200) != WIT_HAL_OK) Serial.print("\r\nSet Baud Error\r\n");
              else 
              {
                 Serial1.begin(c_uiBaud[WIT_BAUD_115200]);
                 Serial.print(" 115200 Baud rate modified successfully\r\n");
              }
			break;
		case 'b':	if(WitSetUartBaud(WIT_BAUD_9600) != WIT_HAL_OK) Serial.print("\r\nSet Baud Error\r\n");
              else 
              {
                Serial1.begin(c_uiBaud[WIT_BAUD_9600]);
                Serial.print(" 9600 Baud rate modified successfully\r\n");
              }
			break;
		case 'h':	ShowHelp();
			break;
		default :return;
	}
	s_cCmd = 0xff;
}
static void RS485_IO_Init(void)
{
  pinMode(21, OUTPUT);
}

static void SensorUartSend(uint8_t *p_data, uint32_t uiSize)
{
  digitalWrite(21, HIGH);
  Serial1.write(p_data, uiSize);
  Serial1.flush();
  digitalWrite(21, LOW);
}

static void Delayms(uint16_t ucMs)
{
  delay(ucMs);
}

static void CopeSensorData(uint32_t uiReg, uint32_t uiRegNum)
{
	int i;
    for(i = 0; i < uiRegNum; i++)
    {
        switch(uiReg)
        {
            case AZ:
				s_cDataUpdate |= ACC_UPDATE;
            break;
            case GZ:
				s_cDataUpdate |= GYRO_UPDATE;
            break;
            case VZ:
				s_cDataUpdate |= VEL_UPDATE;
            break;
            case DZ:
        s_cDataUpdate |= DIS_UPDATE;
            break;
            case ADZ:
				s_cDataUpdate |= ANGLE_UPDATE;
            break;
            case HZZ:
        s_cDataUpdate |= HZ_UPDATE;
            break;
            case TEMP:
        s_cDataUpdate |= TEMP_UPDATE;
            break;
            default:
				s_cDataUpdate |= READ_UPDATE;
			break;
        }
		uiReg++;
    }
}

static void AutoScanSensor(void)
{
	int i, iRetry;
	
	for(i = 0; i < sizeof(c_uiBaud)/sizeof(c_uiBaud[0]); i++)
	{
		Serial1.begin(c_uiBaud[i]);
    Serial1.flush();
		iRetry = 2;
		s_cDataUpdate = 0;
		do
		{
			WitReadReg(ADX, 3);
			delay(200);
			while (Serial1.available())
			{
				WitSerialDataIn(Serial1.read());
			}
			if(s_cDataUpdate != 0)
			{
				Serial.print(c_uiBaud[i]);
				Serial.print(" baud find sensor\r\n\r\n");
				ShowHelp();
				return ;
			}
			iRetry--;
		}while(iRetry);		
	}
	Serial.print("can not find sensor\r\n");
	Serial.print("please check your connection\r\n");
}
