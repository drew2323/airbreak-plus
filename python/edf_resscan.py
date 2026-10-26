#!/usr/bin/env python3
"""
Convert an airbreak EDF superset SD-card to original ResScan EDF layouts.

Usage: edf_resscan.py INPUT_DIRECTORY OUTPUT_DIRECTORY

"""

import argparse
import json
import binascii
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
import math
import os
from pathlib import Path
import re
import shutil
import struct
import zlib


# Channel order from ResScan 7.1 M36/M40 device metadata, expressed as EDF labels.
# Crc16 is the final signal in each layout.
STR_M36_V11 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.BL.StartPress S.BL.IPAP S.BL.EPAP S.EasyBreathe "
    "S.RiseEnable S.RiseTime S.Cycle S.Trigger S.TiMax S.TiMin S.SmartStart S.PtAccess "
    "S.ABFilter S.LeakAlert S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable "
    "S.Temp HeatedTube Humidifier BlowPress.95 BlowPress.5 Flow.95 Flow.5 BlowFlow.50 "
    "AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 SpO2.50 SpO2.95 SpO2.Max "
    "SpO2Thresh MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max "
    "TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max MinVent.50 MinVent.95 "
    "MinVent.Max RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 TidVol.Max IERatio.50 "
    "IERatio.95 IERatio.Max Ti.50 Ti.95 Ti.Max AHI HI AI OAI CAI UAI Fault.Device Fault.Alarm "
    "Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

BRP_M36_V11 = (
    "Flow.40ms Press.40ms Crc16 "
).split()

PLD_M36_V11 = (
    "MaskPress.2s Press.2s EprPress.2s Leak.2s RespRate.2s TidVol.2s MinVent.2s IERatio.2s "
    "Snore.2s B5ITime.2s B5ETime.2s Ti.2s Crc16 "
).split()

SAD_M36_V11 = (
    "Pulse.1s SpO2.1s Crc16 "
).split()

STR_M36_V12 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.BL.StartPress S.BL.IPAP S.BL.EPAP S.BL.BackupRate "
    "S.BL.RespRate S.RiseEnable S.RiseTime S.Cycle S.Trigger S.TiMax S.TiMin S.Ti S.SmartStart "
    "S.PtAccess S.ABFilter S.LeakAlert S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel "
    "S.TempEnable S.Temp S.ExternalHum HeatedTube Humidifier BlowPress.95 BlowPress.5 Flow.95 "
    "Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 SpO2.50 "
    "SpO2.95 SpO2.Max SpO2Thresh SpontTrig% SpontCyc% MaskPress.50 MaskPress.95 MaskPress.Max "
    "TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 "
    "Leak.70 Leak.Max MinVent.50 MinVent.95 MinVent.Max RespRate.50 RespRate.95 RespRate.Max "
    "TidVol.50 TidVol.95 TidVol.Max IERatio.50 IERatio.95 IERatio.Max Ti.50 Ti.95 Ti.Max AHI HI "
    "AI Fault.Device Fault.Alarm Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

STR_M36_V19 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.AV.StartPress S.AV.EPAP S.AV.MaxPS S.AV.MinPS "
    "S.AA.StartPress S.AA.MaxEPAP S.AA.MinEPAP S.AA.MaxPS S.AA.MinPS S.SmartStart S.PtAccess "
    "S.ABFilter S.LeakAlert S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable "
    "S.Temp S.ExternalHum HeatedTube Humidifier BlowPress.95 BlowPress.5 Flow.95 Flow.5 "
    "BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 SpO2.50 SpO2.95 "
    "SpO2.Max SpO2Thresh MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 TgtIPAP.95 "
    "TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max MinVent.50 "
    "MinVent.95 MinVent.Max RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 TidVol.Max "
    "TgtVent.50 TgtVent.95 TgtVent.Max AHI HI AI Fault.Device Fault.Alarm Fault.Humidifier "
    "Fault.HeatedTube Crc16 "
).split()

PLD_M36_V19 = (
    "MaskPress.2s Press.2s EprPress.2s Leak.2s RespRate.2s TidVol.2s MinVent.2s TgtVent.2s "
    "Snore.2s FlowLim.2s Crc16 "
).split()

STR_M36_V1 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.EPR.ClinEnable S.EPR.EPREnable S.EPR.Level "
    "S.EPR.EPRType S.AS.StartPress S.AS.MaxPress S.AS.MinPress S.SmartStart S.PtAccess "
    "S.ABFilter S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable S.Temp "
    "HeatedTube Humidifier BlowPress.95 BlowPress.5 Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 "
    "HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 SpO2.50 SpO2.95 SpO2.Max SpO2Thresh "
    "MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 "
    "TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max MinVent.50 MinVent.95 MinVent.Max "
    "RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 TidVol.Max AHI HI AI OAI CAI UAI "
    "CSR Fault.Device Fault.Alarm Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

BRP_M36_V1 = (
    "Flow.40ms Crc16 "
).split()

PLD_M36_V1 = (
    "MaskPress.2s Press.2s EprPress.2s Leak.2s RespRate.2s TidVol.2s MinVent.2s Snore.2s "
    "FlowLim.2s Crc16 "
).split()

STR_M36_V25 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.EPR.ClinEnable S.EPR.EPREnable S.EPR.Level "
    "S.EPR.EPRType S.AS.StartPress S.AS.MaxPress S.AS.MinPress S.SmartStart S.PtAccess "
    "S.ABFilter S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable S.Temp "
    "HeatedTube Humidifier BlowPress.95 BlowPress.5 Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 "
    "HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 SpO2.50 SpO2.95 SpO2.Max SpO2Thresh "
    "MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 "
    "TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max MinVent.50 MinVent.95 MinVent.Max "
    "RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 TidVol.Max AHI HI AI OAI CAI UAI "
    "RIN CSR Fault.Device Fault.Alarm Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

STR_M36_V26 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.EPR.ClinEnable S.EPR.EPREnable S.EPR.Level "
    "S.EPR.EPRType S.AS.Comfort S.AS.StartPress S.AS.MaxPress S.AS.MinPress S.SmartStart "
    "S.PtAccess S.ABFilter S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable "
    "S.Temp HeatedTube Humidifier BlowPress.95 BlowPress.5 Flow.95 Flow.5 BlowFlow.50 "
    "AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 SpO2.50 SpO2.95 SpO2.Max "
    "SpO2Thresh MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max "
    "TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max MinVent.50 MinVent.95 "
    "MinVent.Max RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 TidVol.Max AHI HI AI "
    "OAI CAI UAI CSR Fault.Device Fault.Alarm Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

STR_M36_V27 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.EPR.ClinEnable S.EPR.EPREnable S.EPR.Level "
    "S.EPR.EPRType S.BL.StartPress S.BL.IPAP S.BL.EPAP S.EasyBreathe S.BL.BackupRate "
    "S.VA.StartPress S.VA.MaxIPAP S.VA.MinEPAP S.VA.PS S.RiseEnable S.RiseTime S.Cycle "
    "S.Trigger S.TiMax S.TiMin S.SmartStart S.PtAccess S.ABFilter S.LeakAlert S.Mask S.Tube "
    "S.ClimateControl S.HumEnable S.HumLevel S.TempEnable S.Temp HeatedTube Humidifier "
    "BlowPress.95 BlowPress.5 Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 "
    "HTubePow.50 HumPow.50 SpO2.50 SpO2.95 SpO2.Max SpO2Thresh SpontTrig% SpontCyc% "
    "MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 "
    "TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max MinVent.50 MinVent.95 MinVent.Max "
    "RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 TidVol.Max IERatio.50 IERatio.95 "
    "IERatio.Max Ti.50 Ti.95 Ti.Max AHI HI AI OAI CAI UAI Fault.Device Fault.Alarm "
    "Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

PLD_M36_V27 = (
    "MaskPress.2s Press.2s EprPress.2s Leak.2s RespRate.2s TidVol.2s MinVent.2s IERatio.2s "
    "Snore.2s FlowLim.2s B5ITime.2s B5ETime.2s Ti.2s Crc16 "
).split()

STR_M36_V28 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.BL.StartPress S.BL.IPAP S.BL.EPAP S.BL.BackupRate "
    "S.RiseEnable S.RiseTime S.Cycle S.Trigger S.TiMax S.TiMin S.SmartStart S.PtAccess "
    "S.ABFilter S.LeakAlert S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable "
    "S.Temp HeatedTube Humidifier BlowPress.95 BlowPress.5 Flow.95 Flow.5 BlowFlow.50 "
    "AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 SpO2.50 SpO2.95 SpO2.Max "
    "SpO2Thresh SpontTrig% SpontCyc% MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 "
    "TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max "
    "MinVent.50 MinVent.95 MinVent.Max RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 "
    "TidVol.Max IERatio.50 IERatio.95 IERatio.Max Ti.50 Ti.95 Ti.Max AHI HI AI Fault.Device "
    "Fault.Alarm Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

STR_M36_V2 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.EPR.ClinEnable S.EPR.EPREnable S.EPR.Level "
    "S.EPR.EPRType S.SmartStart S.PtAccess S.ABFilter S.Mask S.Tube S.ClimateControl "
    "S.HumEnable S.HumLevel S.TempEnable S.Temp HeatedTube Humidifier BlowPress.95 BlowPress.5 "
    "Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 "
    "SpO2.50 SpO2.95 SpO2.Max SpO2Thresh MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 "
    "TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max "
    "MinVent.50 MinVent.95 MinVent.Max RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 "
    "TidVol.Max AHI HI AI OAI CAI UAI CSR Fault.Device Fault.Alarm Fault.Humidifier "
    "Fault.HeatedTube Crc16 "
).split()

STR_M36_V34 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.EPR.ClinEnable S.EPR.EPREnable S.EPR.Level "
    "S.EPR.EPRType S.AS.Comfort S.AS.StartPress S.AS.MaxPress S.AS.MinPress S.SmartStart "
    "S.PtAccess S.ABFilter S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable "
    "S.Temp HeatedTube Humidifier BlowPress.95 BlowPress.5 Flow.95 Flow.5 BlowFlow.50 "
    "AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 SpO2.50 SpO2.95 SpO2.Max "
    "SpO2Thresh MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max "
    "TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max MinVent.50 MinVent.95 "
    "MinVent.Max RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 TidVol.Max AHI HI AI "
    "OAI CAI UAI RIN CSR Fault.Device Fault.Alarm Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

STR_M36_V35 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.EPR.ClinEnable S.EPR.EPREnable S.EPR.Level "
    "S.EPR.EPRType S.PtAccess S.ABFilter S.Mask S.Tube S.HumEnable S.HumLevel Humidifier "
    "BlowPress.95 BlowPress.5 Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HumPow.50 "
    "MaskPress.50 MaskPress.95 MaskPress.Max Leak.95 Leak.70 AHI Fault.Device Fault.Alarm "
    "Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

STR_M36_V36 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.EPR.ClinEnable S.EPR.EPREnable S.EPR.Level "
    "S.EPR.EPRType S.AS.StartPress S.AS.MaxPress S.AS.MinPress S.PtAccess S.ABFilter S.Mask "
    "S.Tube S.HumEnable S.HumLevel Humidifier BlowPress.95 BlowPress.5 Flow.95 Flow.5 "
    "BlowFlow.50 AmbHumidity.50 HumTemp.50 HumPow.50 MaskPress.50 MaskPress.95 MaskPress.Max "
    "TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.95 Leak.70 AHI "
    "Fault.Device Fault.Alarm Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

STR_M36_V38 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.EPR.ClinEnable S.EPR.EPREnable S.EPR.Level "
    "S.EPR.EPRType S.SmartStart S.PtAccess S.ABFilter S.Mask S.Tube S.ClimateControl "
    "S.HumEnable S.HumLevel S.TempEnable S.Temp HeatedTube Humidifier BlowPress.95 BlowPress.5 "
    "Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 "
    "SpO2.50 SpO2.95 SpO2.Max SpO2Thresh MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 "
    "TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max "
    "MinVent.50 MinVent.95 MinVent.Max RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 "
    "TidVol.Max AHI HI AI OAI CAI UAI RIN CSR Fault.Device Fault.Alarm Fault.Humidifier "
    "Fault.HeatedTube Crc16 "
).split()

STR_M36_V3 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.EPR.ClinEnable S.EPR.EPREnable S.EPR.Level "
    "S.EPR.EPRType S.SmartStart S.PtAccess S.ABFilter S.Mask S.Tube S.ClimateControl "
    "S.HumEnable S.HumLevel S.TempEnable S.Temp HeatedTube Humidifier BlowPress.95 BlowPress.5 "
    "Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 "
    "SpO2.50 SpO2.95 SpO2.Max SpO2Thresh MaskPress.50 MaskPress.95 MaskPress.Max Leak.95 "
    "Leak.70 AHI Fault.Device Fault.Alarm Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

STR_M36_V5 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.EPR.ClinEnable S.EPR.EPREnable S.EPR.Level "
    "S.EPR.EPRType S.BL.StartPress S.BL.IPAP S.BL.EPAP S.EasyBreathe S.VA.StartPress "
    "S.VA.MaxIPAP S.VA.MinEPAP S.VA.PS S.SmartStart S.PtAccess S.ABFilter S.LeakAlert S.Mask "
    "S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable S.Temp HeatedTube Humidifier "
    "BlowPress.95 BlowPress.5 Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 "
    "HTubePow.50 HumPow.50 SpO2.50 SpO2.95 SpO2.Max SpO2Thresh MaskPress.50 MaskPress.95 "
    "MaskPress.Max TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 "
    "Leak.95 Leak.70 Leak.Max MinVent.50 MinVent.95 MinVent.Max RespRate.50 RespRate.95 "
    "RespRate.Max TidVol.50 TidVol.95 TidVol.Max IERatio.50 IERatio.95 IERatio.Max Ti.50 Ti.95 "
    "Ti.Max AHI HI AI OAI CAI UAI Fault.Device Fault.Alarm Fault.Humidifier Fault.HeatedTube "
    "Crc16 "
).split()

STR_M36_V9 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.EPR.ClinEnable S.EPR.EPREnable S.EPR.Level "
    "S.EPR.EPRType S.BL.StartPress S.BL.IPAP S.BL.EPAP S.EasyBreathe S.VA.StartPress "
    "S.VA.MaxIPAP S.VA.MinEPAP S.VA.PS S.RiseEnable S.RiseTime S.Cycle S.Trigger S.TiMax "
    "S.TiMin S.SmartStart S.PtAccess S.ABFilter S.LeakAlert S.Mask S.Tube S.ClimateControl "
    "S.HumEnable S.HumLevel S.TempEnable S.Temp HeatedTube Humidifier BlowPress.95 BlowPress.5 "
    "Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 "
    "SpO2.50 SpO2.95 SpO2.Max SpO2Thresh SpontCyc% MaskPress.50 MaskPress.95 MaskPress.Max "
    "TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 "
    "Leak.70 Leak.Max MinVent.50 MinVent.95 MinVent.Max RespRate.50 RespRate.95 RespRate.Max "
    "TidVol.50 TidVol.95 TidVol.Max IERatio.50 IERatio.95 IERatio.Max Ti.50 Ti.95 Ti.Max AHI HI "
    "AI OAI CAI UAI Fault.Device Fault.Alarm Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

STR_M40_V41 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.RampDownEnable S.C.StartPress S.C.Press S.BL.StartPress S.BL.IPAP S.BL.EPAP "
    "S.BL.BackupRate S.RiseEnable S.RiseTime S.Cycle S.Trigger S.TiMax S.TiMin S.SmartStart "
    "S.PtAccess S.ABFilter S.LeakAlert S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel "
    "S.TempEnable S.Temp S.ExternalHum HeatedTube Humidifier ODIThreshold BlowPress.95 "
    "BlowPress.5 Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 "
    "HumPow.50 HeartRate.50 HeartRate.Max HeartRate.95 SpO2.50 SpO2.95 SpO2.Max SpO2.Min "
    "SpO2Thresh SpontTrig% SpontCyc% MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 "
    "TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max "
    "MinVent.50 MinVent.95 MinVent.Max RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 "
    "TidVol.Max IERatio.50 IERatio.95 IERatio.Max Ti.50 Ti.95 Ti.Max AHI HI AI ODI Oxy.Dur "
    "Fault.Device Fault.Alarm Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

PLD_M40_V41 = (
    "MaskPress.2s Press.2s EprPress.2s Leak.2s RespRate.2s TidVol.2s MinVent.2s IERatio.2s "
    "B5ITime.2s B5ETime.2s Ti.2s CLRatio.2s TRRatio.2s Crc16 "
).split()

STR_M40_V43 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.RampDownEnable S.C.StartPress S.C.Press S.BL.StartPress S.BL.IPAP S.BL.EPAP "
    "S.BL.IBR S.BL.TgtRR S.BL.BackupRate S.BL.RespRate S.RiseEnable S.RiseTime S.Cycle "
    "S.Trigger S.TiMax S.TiMin S.Ti S.SmartStart S.PtAccess S.ABFilter S.LeakAlert S.Mask "
    "S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable S.Temp S.ExternalHum "
    "HeatedTube Humidifier ODIThreshold BlowPress.95 BlowPress.5 Flow.95 Flow.5 BlowFlow.50 "
    "AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 HeartRate.50 HeartRate.Max "
    "HeartRate.95 SpO2.50 SpO2.95 SpO2.Max SpO2.Min SpO2Thresh SpontTrig% SpontCyc% "
    "MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 "
    "TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max MinVent.50 MinVent.95 MinVent.Max "
    "RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 TidVol.Max IERatio.50 IERatio.95 "
    "IERatio.Max Ti.50 Ti.95 Ti.Max AHI HI AI ODI Oxy.Dur Fault.Device Fault.Alarm "
    "Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

STR_M40_V44 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.RampDownEnable S.C.StartPress S.C.Press S.BL.StartPress S.BL.IPAP S.BL.EPAP "
    "S.BL.IBR S.BL.TgtRR S.BL.BackupRate S.i.StartPress S.i.EPAP S.i.EPAPAuto S.i.MaxPS "
    "S.i.MinPS S.i.MinEPAP S.i.MaxEPAP S.i.Height S.i.AlvMinVent S.i.RespRate S.BL.RespRate "
    "S.RiseEnable S.RiseTime S.Cycle S.Trigger S.TiMax S.TiMin S.Ti S.SmartStart S.PtAccess "
    "S.ABFilter S.LeakAlert S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable "
    "S.Temp S.ExternalHum HeatedTube Humidifier ODIThreshold BlowPress.95 BlowPress.5 Flow.95 "
    "Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 "
    "HeartRate.50 HeartRate.Max HeartRate.95 SpO2.50 SpO2.95 SpO2.Max SpO2.Min SpO2Thresh "
    "SpontTrig% SpontCyc% MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 TgtIPAP.95 "
    "TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max MinVent.50 "
    "MinVent.95 MinVent.Max RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 TidVol.Max "
    "IERatio.50 IERatio.95 IERatio.Max AlvMinVent.50 AlvMinVent.95 AlvMinVent.Max Ti.50 Ti.95 "
    "Ti.Max AHI HI AI ODI Oxy.Dur Fault.Device Fault.Alarm Fault.Humidifier Fault.HeatedTube "
    "Crc16 "
).split()

PLD_M40_V44 = (
    "MaskPress.2s Press.2s EprPress.2s Leak.2s RespRate.2s TidVol.2s MinVent.2s IERatio.2s "
    "B5ITime.2s B5ETime.2s AlvMinVent.2s Ti.2s CLRatio.2s TRRatio.2s Crc16 "
).split()

STR_M40_V45 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.RampDownEnable S.C.StartPress S.C.Press S.BL.StartPress S.BL.IPAP S.BL.EPAP "
    "S.BL.IBR S.BL.TgtRR S.BL.BackupRate S.BL.RespRate S.RiseEnable S.RiseTime S.Cycle "
    "S.Trigger S.TiMax S.TiMin S.Ti S.SmartStart S.PtAccess S.ABFilter S.Mask S.Tube "
    "S.ClimateControl S.HumEnable S.HumLevel S.TempEnable S.Temp S.ExternalHum HeatedTube "
    "Humidifier ODIThreshold NVMask.Alm.En HiLeak.Alm.En LowMV.Alm.Thres LowMV.Alm.En "
    "Apnea.Alm.Thres Apnea.Alm.En Alm.Vol Spo2.Alm.Thres Spo2.Alm.En BlowPress.95 BlowPress.5 "
    "Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 "
    "HeartRate.50 HeartRate.Max HeartRate.95 SpO2.50 SpO2.95 SpO2.Max SpO2.Min SpO2Thresh "
    "SpontTrig% SpontCyc% MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 TgtIPAP.95 "
    "TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max MinVent.50 "
    "MinVent.95 MinVent.Max RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 TidVol.Max "
    "IERatio.50 IERatio.95 IERatio.Max Ti.50 Ti.95 Ti.Max AHI HI AI ODI Oxy.Dur Fault.Device "
    "Fault.Alarm Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

STR_M40_V46 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.RampDownEnable S.C.StartPress S.C.Press S.BL.StartPress S.BL.IPAP S.BL.EPAP "
    "S.BL.IBR S.BL.TgtRR S.BL.BackupRate S.i.StartPress S.i.EPAP S.i.EPAPAuto S.i.MaxPS "
    "S.i.MinPS S.i.MinEPAP S.i.MaxEPAP S.i.Height S.i.AlvMinVent S.i.RespRate S.BL.RespRate "
    "S.RiseEnable S.RiseTime S.Cycle S.Trigger S.TiMax S.TiMin S.Ti S.SmartStart S.PtAccess "
    "S.ABFilter S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable S.Temp "
    "S.ExternalHum HeatedTube Humidifier ODIThreshold NVMask.Alm.En HiLeak.Alm.En "
    "LowMV.Alm.Thres LowMV.Alm.En Apnea.Alm.Thres Apnea.Alm.En Alm.Vol Spo2.Alm.Thres "
    "Spo2.Alm.En BlowPress.95 BlowPress.5 Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 "
    "HTubeTemp.50 HTubePow.50 HumPow.50 HeartRate.50 HeartRate.Max HeartRate.95 SpO2.50 SpO2.95 "
    "SpO2.Max SpO2.Min SpO2Thresh SpontTrig% SpontCyc% MaskPress.50 MaskPress.95 MaskPress.Max "
    "TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 "
    "Leak.70 Leak.Max MinVent.50 MinVent.95 MinVent.Max RespRate.50 RespRate.95 RespRate.Max "
    "TidVol.50 TidVol.95 TidVol.Max IERatio.50 IERatio.95 IERatio.Max AlvMinVent.50 "
    "AlvMinVent.95 AlvMinVent.Max Ti.50 Ti.95 Ti.Max AHI HI AI ODI Oxy.Dur Fault.Device "
    "Fault.Alarm Fault.Humidifier Fault.HeatedTube Crc16 "
).split()

STR_M40_V49 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.RampDownEnable S.C.StartPress S.C.Press S.BL.StartPress S.BL.IPAP S.BL.EPAP "
    "S.BL.IBR S.BL.TgtRR S.BL.BackupRate S.i.StartPress S.i.EPAP S.i.MaxPS S.i.MinPS "
    "S.i.MinEPAP S.i.MaxEPAP S.i.Height S.i.AlvMinVent S.i.RespRate S.BL.RespRate S.RiseEnable "
    "S.RiseTime S.Cycle S.Trigger S.TiMax S.TiMin S.Ti S.SmartStart S.PtAccess S.ABFilter "
    "S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable S.Temp S.ExternalHum "
    "HeatedTube Humidifier ODIThreshold NVMask.Alm.En HiLeak.Alm.En LowMV.Alm.Thres "
    "LowMV.Alm.En Apnea.Alm.Thres Apnea.Alm.En Alm.Vol Spo2.Alm.Thres Spo2.Alm.En BlowPress.95 "
    "BlowPress.5 Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 "
    "HumPow.50 HeartRate.50 HeartRate.Max HeartRate.95 SpO2.50 SpO2.95 SpO2.Max SpO2.Min "
    "SpO2Thresh SpontTrig% SpontCyc% MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 "
    "TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max "
    "MinVent.50 MinVent.95 MinVent.Max RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 "
    "TidVol.Max IERatio.50 IERatio.95 IERatio.Max AlvMinVent.50 AlvMinVent.95 AlvMinVent.Max "
    "Ti.50 Ti.95 Ti.Max AHI HI AI ODI Oxy.Dur Fault.Device Fault.Alarm Fault.Humidifier "
    "Fault.HeatedTube Crc16 "
).split()

STR_M40_V50 = (
    "Date MaskOn MaskOff MaskEvents Duration OnDuration PatientHours Mode S.RampEnable "
    "S.RampTime S.C.StartPress S.C.Press S.AV.StartPress S.AV.EPAP S.AV.MaxPS S.AV.MinPS "
    "S.AA.StartPress S.AA.MaxEPAP S.AA.MinEPAP S.AA.MaxPS S.AA.MinPS S.SmartStart S.PtAccess "
    "S.ABFilter S.Mask S.Tube S.ClimateControl S.HumEnable S.HumLevel S.TempEnable S.Temp "
    "S.ExternalHum HeatedTube Humidifier ODIThreshold NVMask.Alm.En HiLeak.Alm.En "
    "LowMV.Alm.Thres LowMV.Alm.En Alm.Vol Spo2.Alm.Thres Spo2.Alm.En BlowPress.95 BlowPress.5 "
    "Flow.95 Flow.5 BlowFlow.50 AmbHumidity.50 HumTemp.50 HTubeTemp.50 HTubePow.50 HumPow.50 "
    "HeartRate.50 HeartRate.Max HeartRate.95 SpO2.50 SpO2.95 SpO2.Max SpO2.Min SpO2Thresh "
    "MaskPress.50 MaskPress.95 MaskPress.Max TgtIPAP.50 TgtIPAP.95 TgtIPAP.Max TgtEPAP.50 "
    "TgtEPAP.95 TgtEPAP.Max Leak.50 Leak.95 Leak.70 Leak.Max MinVent.50 MinVent.95 MinVent.Max "
    "RespRate.50 RespRate.95 RespRate.Max TidVol.50 TidVol.95 TidVol.Max TgtVent.50 TgtVent.95 "
    "TgtVent.Max AHI HI AI ODI Oxy.Dur Fault.Device Fault.Alarm Fault.Humidifier "
    "Fault.HeatedTube Crc16 "
).split()

# Air11 M46/V3 is the AutoSet-family profile used for CPAP/AutoSet/For Her.
# The Airbreak EDF superset preserves stock ordering and adds rows, so a
# V3-compatible layout can be recovered by removing rows that provenance marks
# as VA/ST/ASV-only.
AS11_V3_STR_EXCLUDE_PREFIXES = (
    "S.VA.", "S.S.", "S.ST.", "S.T.", "S.AV.", "S.AA.",
    "SpontTrig%", "SpontCyc%", "TgtVent.", "IERatio.", "Ti.",
)
AS11_V3_PLD_EXCLUDE_PREFIXES = ("TgtVent.", "IERatio.", "Ti.")


def str_m46_v3(names):
    return tuple(name for name in names
                 if not name.startswith(AS11_V3_STR_EXCLUDE_PREFIXES))


def pld_m46_v3(names):
    return tuple(name for name in names
                 if not name.startswith(AS11_V3_PLD_EXCLUDE_PREFIXES))


# Decimal MID/VID profiles: native MOP options and EDF channel layouts.
PROFILES = {
    (36, 1): {'modes': {0, 1}, 'STR': STR_M36_V1, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 2): {'modes': {0}, 'STR': STR_M36_V2, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 3): {'modes': {0}, 'STR': STR_M36_V3},
    (36, 5): {'modes': {0, 3, 6}, 'STR': STR_M36_V5, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V27, 'SAD': SAD_M36_V11},
    (36, 7): {'modes': {0, 3, 4, 5}, 'STR': STR_M36_V12, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V11, 'SAD': SAD_M36_V11},
    (36, 9): {'modes': {0, 3, 6}, 'STR': STR_M36_V9, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V27, 'SAD': SAD_M36_V11},
    (36, 11): {'modes': {0, 3}, 'STR': STR_M36_V11, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V11, 'SAD': SAD_M36_V11},
    (36, 12): {'modes': {0, 3, 4, 5}, 'STR': STR_M36_V12, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V11, 'SAD': SAD_M36_V11},
    (36, 19): {'modes': {0, 7, 8}, 'STR': STR_M36_V19, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V19, 'SAD': SAD_M36_V11},
    (36, 25): {'modes': {0, 1, 11}, 'STR': STR_M36_V25, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 26): {'modes': {0, 1}, 'STR': STR_M36_V26, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 27): {'modes': {0, 3, 6}, 'STR': STR_M36_V27, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V27, 'SAD': SAD_M36_V11},
    (36, 28): {'modes': {0, 3}, 'STR': STR_M36_V28, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V11, 'SAD': SAD_M36_V11},
    (36, 34): {'modes': {0, 1, 11}, 'STR': STR_M36_V34, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 35): {'modes': {0}, 'STR': STR_M36_V35},
    (36, 36): {'modes': {0, 2}, 'STR': STR_M36_V36},
    (36, 37): {'modes': {0, 1}, 'STR': STR_M36_V25, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 38): {'modes': {0}, 'STR': STR_M36_V38, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 39): {'modes': {0, 1}, 'STR': STR_M36_V34, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (40, 41): {'modes': {0, 3}, 'STR': STR_M40_V41, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V41, 'SAD': SAD_M36_V11},
    (40, 43): {'modes': {0, 3, 4, 5, 10}, 'STR': STR_M40_V43, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V41, 'SAD': SAD_M36_V11},
    (40, 44): {'modes': {0, 3, 4, 5, 9, 10}, 'STR': STR_M40_V44, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V44, 'SAD': SAD_M36_V11},
    (40, 45): {'modes': {0, 3, 4, 5, 10}, 'STR': STR_M40_V45, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V41, 'SAD': SAD_M36_V11},
    (40, 46): {'modes': {0, 3, 4, 5, 9, 10}, 'STR': STR_M40_V46, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V44, 'SAD': SAD_M36_V11},
    (40, 48): {'modes': {0, 3, 4, 5, 9, 10}, 'STR': STR_M40_V46, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V44, 'SAD': SAD_M36_V11},
    (40, 49): {'modes': {0, 3, 4, 5, 9, 10}, 'STR': STR_M40_V49, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V44, 'SAD': SAD_M36_V11},
    (40, 50): {'modes': {0, 7, 8}, 'STR': STR_M40_V50, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V19, 'SAD': SAD_M36_V11},
    (40, 51): {'modes': {0, 7, 8}, 'STR': STR_M40_V50, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V19, 'SAD': SAD_M36_V11},
    # Air11 AutoSet family. Air11 EDF maps raw MOP=0 (CPAP) to exported Mode=3.
    (46, 3): {'modes': {0, 1, 2}, 'STR': str_m46_v3,
              'BRP': None, 'PLD': pld_m46_v3, 'SA2': None},
}


SIGNAL_FIELD_WIDTHS = (16, 80, 8, 8, 8, 8, 8, 80, 8, 32)

# Detailed samples approximate these summaries; native STR uses other sampling
# rates and histogram bins. Settings and lifetime counters cannot be recovered.
SUMMARY_CHANNELS = {
    'MaskPress.2s': 'MaskPress', 'Press.2s': 'TgtIPAP',
    'EprPress.2s': 'TgtEPAP', 'Leak.2s': 'Leak',
    'RespRate.2s': 'RespRate', 'TidVol.2s': 'TidVol',
    'MinVent.2s': 'MinVent', 'IERatio.2s': 'IERatio',
    'Ti.2s': 'Ti', 'TgtVent.2s': 'TgtVent',
    'AlvMinVent.2s': 'AlvMinVent', 'Pulse.1s': 'HeartRate',
    'SpO2.1s': 'SpO2',
}
EVENT_INDEX = {'Obstructive Apnea': 'OAI', 'Central Apnea': 'CAI',
               'Apnea': 'UAI', 'Hypopnea': 'HI'}
# Reverse mappings from vid_spoof.c, including the older PAC -> V7 mapping.
SPOOF_MODES = {
    (36, 7): {4, 5, 10}, (36, 9): {6}, (36, 11): {3},
    (36, 19): {7, 8}, (36, 25): {11}, (36, 26): {0, 1, 2},
    (36, 34): {1, 11}, (36, 39): {1}, (36, 46): {9, 10},
}
EPOCH = datetime(1970, 1, 1)


def crc16(data):
    return binascii.crc_hqx(data, 0xffff)


def find_file(directory, name):
    """Find a card file without depending on the host's filename case rules."""
    return next((path for path in directory.iterdir()
                 if path.name.lower() == name.lower()), None)


def original_profile(identification):
    match = re.search(rb'^#FGT\s+\S*_M(\d+)_V(\d+)\s*$', identification, re.M)
    if match is None:
        raise ValueError("Identification.tgt: missing or invalid FGT; use --profile MID:VID")
    return tuple(map(int, match.groups()))



def original_profile_json(data):
    """Read Air11 MID/VID from Identification.json."""
    try:
        root = json.loads(data.decode('utf-8'))
        software = root['FlowGenerator']['IdentificationProfiles']['Software']
        return int(software['PlatformIdentifier']), int(software['VariantIdentifier'])
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise ValueError("Identification.json: missing or invalid Air11 Software identity") from error


def restore_air11_json_identification(data, mid, vid):
    """Rewrite Air11 JSON identity consistently for an M46/V3 CPAP fixture."""
    try:
        root = json.loads(data.decode('utf-8'))
        profiles = root['FlowGenerator']['IdentificationProfiles']
        product = profiles['Product']
        software = profiles['Software']
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as error:
        raise ValueError("Identification.json: invalid Air11 identity tree") from error

    software['PlatformIdentifier'] = int(mid)
    software['VariantIdentifier'] = int(vid)

    configuration = software.get('ConfigurationIdentifier')
    if isinstance(configuration, str):
        parts = configuration.split('.')
        if len(parts) >= 4 and parts[0].startswith('CF'):
            parts[2] = f'{vid:02d}'
            software['ConfigurationIdentifier'] = '.'.join(parts)

    pvi = software.get('ProfileVariationIdentifier')
    if isinstance(pvi, str):
        software['ProfileVariationIdentifier'] = re.sub(
            r'\d{3}$', f'{vid:03d}', pvi)

    if mid == 46 and vid == 3:
        product['ProductName'] = 'AirSense 11 AutoSet'

    return json.dumps(root, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def parse_profile(value):
    match = re.fullmatch(r'(\d+):(\d+)', value)
    if match is None:
        raise argparse.ArgumentTypeError("expected MID:VID in decimal")
    return tuple(map(int, match.groups()))


def restore_identification(data, mid, vid):
    for tag, value in ((b'MID', mid), (b'VID', vid)):
        replacement = b'#' + tag + (' %04X' % value).encode('ascii')
        data, count = re.subn(rb'^#' + tag + rb'\b[^\r\n]*', replacement, data, flags=re.M)
        if count == 0:
            data = data.rstrip(b'\r\n') + b'\r\n' + replacement + b'\r\n'
    return data


def restore_air11_identification(data, mid, vid):
    """Rewrite Air11 identity strings consistently to the requested MID/VID."""
    data = restore_identification(data, mid, vid)

    # FGT: ..._M46_V12 -> ..._M46_V3
    pattern = rb'(^#FGT\s+\S*_M)\d+(_V)\d+([^\r\n]*)'
    data = re.sub(
        pattern,
        lambda m: (m.group(1) + str(mid).encode('ascii') +
                   m.group(2) + str(vid).encode('ascii') + m.group(3)),
        data, count=1, flags=re.M)

    # GCD/CID: VID is the two-digit component after the second dot.
    def dotted(match):
        value = match.group(2)
        parts = value.split(b'.')
        if len(parts) >= 4:
            parts[2] = ('%02d' % vid).encode('ascii')
            value = b'.'.join(parts)
        return match.group(1) + value

    data = re.sub(rb'^(#(?:GCD|CID)\s+)(\S+)', dotted, data, flags=re.M)

    # PVI: last three characters encode VID, zero padded.
    def pvi(match):
        value = match.group(2)
        if len(value) >= 3:
            value = value[:-3] + ('%03d' % vid).encode('ascii')
        return match.group(1) + value

    data = re.sub(rb'^(#PVI\s+)(\S+)', pvi, data, flags=re.M)
    return data


def restore_edf_identification(header, mid, vid):
    recording = bytes(header[88:168]).rstrip(b' ')
    for tag, value in ((b'MID', mid), (b'VID', vid)):
        replacement = tag + b'=' + str(value).encode('ascii')
        recording, count = re.subn(
            rb'(?<!\S)' + tag + rb'=\S*', replacement, recording)
        if count == 0:
            recording += b' ' + replacement
    if len(recording) > 80:
        raise ValueError("EDF recording identification exceeds 80 bytes")
    header[88:168] = recording.ljust(80, b' ')


def read_edf_header(src):
    header = bytearray(src.read(256))
    count = int(header[252:256])
    signal_header = src.read(256 * count)
    fields, offset = [], 0
    for width in SIGNAL_FIELD_WIDTHS:
        fields.append([signal_header[offset + i * width:offset + (i + 1) * width]
                       for i in range(count)])
        offset += width * count
    return header, fields


def signal_spans(samples):
    spans, offset = [], 0
    for count in samples:
        spans.append(slice(offset, offset + 2 * count))
        offset += 2 * count
    return spans, offset


def edf_start(header):
    start = datetime.strptime(header[168:184].decode(), '%d.%m.%y%H.%M.%S')
    return (start - EPOCH).total_seconds()


def signal_scale(fields, index):
    pmin, pmax, dmin, dmax = (float(fields[i][index]) for i in (3, 4, 5, 6))
    scale = (pmax - pmin) / (dmax - dmin)
    return scale, pmin - dmin * scale, dmin, dmax


def empty_str_day(record, names, spans):
    if 'Date' not in names or any(
            record[span] != b'\xff' * (span.stop - span.start)
            for name, span in zip(names, spans) if name not in ('Date', 'Crc16')):
        return None
    day = struct.unpack_from('<H', record, spans[names.index('Date')].start)[0]
    return day if day != 0xffff else None


def edf_profile(header):
    ids = re.search(rb'\bMID=(\d+)\s+VID=(\d+)\b', header[88:168])
    return tuple(map(int, ids.groups())) if ids else None


def mode_candidates(header, factory_profile, active_channels, automatic_pressure=False):
    """Combine original identity, mode-specific channels and pressure evidence."""
    candidates = set(range(12))
    recorded_profile = edf_profile(header)
    if factory_profile and recorded_profile != factory_profile:
        candidates &= SPOOF_MODES.get(recorded_profile, candidates)
    if 'AlvMinVent' in active_channels:
        candidates &= {9}
    if 'TgtVent' in active_channels:
        candidates &= {7, 8}
    if automatic_pressure:
        candidates.discard(0)
    # Native modes are a reconstruction preference, not a restriction on
    # unlocked firmware. Do not override a mode identified by recorded channels.
    if len(candidates) > 1 and (factory_profile is None or recorded_profile == factory_profile):
        native = candidates & PROFILES.get(recorded_profile, {}).get('modes', set())
        if native:
            candidates = native
    return candidates


def resolve_summary_modes(days, known_modes):
    """Prefer nearby known modes, then the highest compatible mode for the VID."""
    hints = dict(known_modes)
    candidates_by_day = {}
    for day, summary in days.items():
        modes = summary['modes']
        candidates = set.intersection(*modes) if modes else set()
        candidates_by_day[day] = candidates
        mode = known_modes.get(day)
        if mode is None and len(candidates) == 1:
            mode = next(iter(candidates))
        summary['mode'] = mode
        if mode is not None:
            hints[day] = mode

    # Keep hints fixed so a fallback choice cannot propagate through history.
    hint_days = sorted(hints)
    for day, summary in days.items():
        candidates = candidates_by_day[day]
        if summary['mode'] is not None or not candidates:
            continue
        i = bisect_left(hint_days, day)
        neighbors = hint_days[max(0, i - 1):i + 1]
        compatible = [(abs(day - other), hints[other]) for other in neighbors
                      if hints[other] in candidates]
        if compatible:
            distance = min(distance for distance, _ in compatible)
            modes = {mode for gap, mode in compatible if gap == distance}
            if len(modes) == 1:
                summary['mode'] = modes.pop()
                continue
        available = set()
        for profile in summary['profiles']:
            available.update(PROFILES.get(profile, {}).get('modes', set()))
            available.update(SPOOF_MODES.get(profile, set()))
        summary['mode'] = max(candidates & available, default=None)


def add_interval(intervals, start, end):
    """Merge a range into sorted coverage, including backfilled gaps."""
    left = bisect_left(intervals, (start,))
    if left and intervals[left - 1][1] >= start:
        left -= 1
    right = left
    while right < len(intervals) and intervals[right][0] <= end:
        start = min(start, intervals[right][0])
        end = max(end, intervals[right][1])
        right += 1
    intervals[left:right] = [(start, end)]


def uncovered_intervals(intervals, start, end):
    """Yield the parts of a sample not supplied by an earlier recording."""
    i = max(0, bisect_right(intervals, (start, float('inf'))) - 1)
    while i < len(intervals) and intervals[i][0] < end:
        a, b = intervals[i]
        if start < a:
            yield start, min(a, end)
        start = max(start, b)
        if start >= end:
            return
        i += 1
    if start < end:
        yield start, end


def reconstruct_str(source, factory_profile):
    """Collect only days whose source STR contains Date/CRC and no data."""
    paths = sorted(path for path in source.rglob('*') if path.suffix.lower() == '.edf')
    days, known_modes = {}, {}
    for path in paths:
        if edf_channel(path) != 'STR':
            continue
        with path.open('rb') as src:
            _, fields = read_edf_header(src)
            names = [value.decode().rstrip() for value in fields[0]]
            spans, size = signal_spans(map(int, fields[8]))
            while record := src.read(size):
                if 'Date' in names and 'Mode' in names:
                    day = struct.unpack_from('<H', record, spans[names.index('Date')].start)[0]
                    mode = struct.unpack_from('<H', record, spans[names.index('Mode')].start)[0]
                    if day != 0xffff and mode in range(12):
                        known_modes[day] = mode
                day = empty_str_day(record, names, spans)
                if day is not None:
                    days[day] = {'intervals': [], 'samples': defaultdict(Counter),
                                 'units': {}, 'modes': [], 'events': set(),
                                 'has_eve': False, 'profiles': set()}
    if not days:
        return days
    files = []
    for path in paths:
        channel = edf_channel(path)
        if channel in ('PLD', 'SAD', 'EVE'):
            with path.open('rb') as src:
                header = src.read(256)
            files.append((edf_start(header), path, channel))
    files.sort()
    # Process pressure coverage first, then restrict oximetry to it.
    seen = defaultdict(list)
    for wanted in ('PLD', 'SAD', 'EVE'):
        for start, path, channel in files:
            if channel != wanted:
                continue
            with path.open('rb') as src:
                header, fields = read_edf_header(src)
                names = [value.decode().rstrip() for value in fields[0]]
                samples = list(map(int, fields[8]))
                spans, size = signal_spans(samples)
                period = float(header[244:252])
                if channel == 'EVE':
                    # The native TAL onset dates event publication, not its
                    # beginning. Count it once, without subtracting duration.
                    annotation = spans[names.index('EDF Annotations')]
                    while record := src.read(size):
                        for tal in record[annotation].split(b'\0'):
                            parts = tal.split(b'\x14')
                            if len(parts) < 2 or not parts[1]:
                                continue
                            time = start + float(parts[0].split(b'\x15')[0])
                            label = parts[1].decode('ascii')
                            # EVE can span several PLD recordings. Assign events
                            # to their therapy day, independently of PLD edges.
                            day = math.floor((time - 43200) / 86400)
                            if day in days:
                                days[day]['has_eve'] = True
                                if label in EVENT_INDEX:
                                    days[day]['events'].add((time, label))
                    continue
                anchor = names.index('MaskPress.2s') if 'MaskPress.2s' in names else None
                active, file_days = defaultdict(set), set()
                late_pressure = {}
                channels = [i for i, name in enumerate(names) if name in SUMMARY_CHANNELS]
                scales = {i: signal_scale(fields, i) for i in channels}
                for record_index, record in enumerate(iter(lambda: src.read(size), b'')):
                    anchor_values = (struct.unpack('<%dH' % samples[anchor], record[spans[anchor]])
                                     if anchor is not None else None)
                    for i in channels:
                        label = SUMMARY_CHANNELS[names[i]]
                        scale, bias, dmin, _ = scales[i]
                        step = period / samples[i]
                        for j, (raw,) in enumerate(struct.iter_unpack('<H', record[spans[i]])):
                            if raw == 0xffff or (anchor_values is not None and
                                    anchor_values[j * len(anchor_values) // samples[i]] == 0xffff):
                                continue
                            time = start + record_index * period + j * step
                            end = time + step
                            # Overlapping copies must not increase duration or
                            # overweight their samples in the daily percentiles.
                            coverage = seen[channel, label]
                            uncovered = list(uncovered_intervals(coverage, time, end))
                            if not uncovered:
                                continue
                            add_interval(coverage, time, end)
                            value = (raw - 65536 if dmin < 0 and raw >= 32768 else raw) * scale + bias
                            for time, end in uncovered:
                                while time < end:
                                    day = math.floor((time - 43200) / 86400)
                                    stop = min(end, (day + 1) * 86400 + 43200)
                                    summary = days.get(day)
                                    if summary is not None:
                                        weight = stop - time
                                        if channel == 'SAD':
                                            weight = sum(max(0, min(stop, b) - max(time, a))
                                                         for a, b in summary['intervals'])
                                        if weight:
                                            summary['samples'][label][value] += weight
                                            summary['units'][label] = fields[2][i].strip()
                                            active[day].add(label)
                                            # Infer adaptation within one recording,
                                            # excluding the first 45 minutes (ramp).
                                            if label == 'TgtIPAP' and time - start >= 45 * 60:
                                                low, high = late_pressure.get(day, (value, value))
                                                late_pressure[day] = min(low, value), max(high, value)
                                            if i == anchor:
                                                add_interval(summary['intervals'], time, stop)
                                                file_days.add(day)
                                    time = stop
                if channel == 'PLD':
                    for day in file_days:
                        low, high = late_pressure.get(day, (0, 0))
                        # A 0.5 cmH2O excursion avoids treating small reporting
                        # fluctuations as automatic pressure adjustment.
                        candidates = mode_candidates(header, factory_profile, active[day],
                                                     automatic_pressure=high - low >= 0.5)
                        days[day]['modes'].append(candidates)
                        days[day]['profiles'].add(edf_profile(header) or factory_profile)
    resolve_summary_modes(days, known_modes)
    return days


def repair_str_record(record, fields, summaries):
    names = [value.decode().rstrip() for value in fields[0]]
    spans, _ = signal_spans(map(int, fields[8]))
    day = empty_str_day(record, names, spans)
    summary = summaries.get(day)
    if summary is None or not summary['intervals']:
        return record
    result = bytearray(record)

    def put(name, values, unit=None):
        if name not in names:
            return
        i = names.index(name)
        if unit is not None and unit != fields[2][i].strip():
            return
        scale, bias, dmin, dmax = signal_scale(fields, i)
        for j, value in enumerate(values[:int(fields[8][i])]):
            raw = round((value - bias) / scale)
            if dmin <= raw <= dmax and (raw & 0xffff) != 0xffff:
                struct.pack_into('<H', result, spans[i].start + 2 * j, raw & 0xffff)

    intervals = summary['intervals']
    seconds = sum(b - a for a, b in intervals)
    noon = day * 86400 + 43200
    # Recording intervals approximate mask use; they cannot reproduce MST=2
    # pause merging. Do not infer blower-on time or the lifetime hour counter.
    put('Duration', [seconds / 60])
    if all(name in names for name in ('MaskOn', 'MaskOff')) and len(intervals) <= min(
            int(fields[8][names.index(name)]) for name in ('MaskOn', 'MaskOff')):
        put('MaskOn', [(a - noon) / 60 for a, _ in intervals])
        put('MaskOff', [(b - noon) / 60 for _, b in intervals])
        put('MaskEvents', [2 * len(intervals)])
    mode = summary['mode']
    if mode is not None:
        put('Mode', [mode])
    for label, histogram in summary['samples'].items():
        ordered = sorted(histogram.items())
        total = sum(histogram.values())
        for suffix, percentile in (('Min', 0), ('50', .5), ('70', .7), ('95', .95), ('Max', 1)):
            cumulative = 0
            for value, weight in ordered:
                cumulative += weight
                if cumulative >= total * percentile:
                    put(label + '.' + suffix, [value], summary['units'][label])
                    break
    # No EVE for this day means unknown event indices, not zero events.
    if summary['has_eve']:
        counts = Counter(EVENT_INDEX[label] for _, label in summary['events'])
        counts['AI'] = counts['OAI'] + counts['CAI'] + counts['UAI']
        counts['AHI'] = counts['AI'] + counts['HI']
        for label in ('OAI', 'CAI', 'UAI', 'HI', 'AI', 'AHI'):
            put(label, [counts[label] * 3600 / seconds])
    return bytes(result)


SYNTHETIC_CPAP_DETAILED_PRESSURE = (
    'Press.40ms',
    'MaskPress.2s',
    'Press.2s',
    'EprPress.2s',
)

SYNTHETIC_CPAP_STR_PRESSURE = (
    'S.C.StartPress',
    'S.C.Press',
    'BlowPress.95',
    'BlowPress.5',
    'MaskPress.50',
    'MaskPress.95',
    'MaskPress.Max',
    'TgtIPAP.50',
    'TgtIPAP.95',
    'TgtIPAP.Max',
    'TgtEPAP.50',
    'TgtEPAP.95',
    'TgtEPAP.Max',
)


FLOW_PRESSURE_LOW = 6.4
FLOW_PRESSURE_HIGH = 7.9
# Frozen from the current fixture's |Flow.40ms| distribution: >=1.8 L/s
# onset, linearly saturating at 2.4 L/s. Events are contiguous threshold hits,
# allowing at most two intervening 40 ms samples (120 ms grouping window).
FLOW_RARE_PEAK_ONSET_LPS = 1.8
FLOW_RARE_PEAK_SATURATION_LPS = 2.4
FLOW_RARE_PEAK_MAX_AT_7_5 = 9.5


class FlowPressureModel:
    """Deterministic signed-flow heuristic; not a physiology model."""
    def __init__(self, baseline, flow_samples):
        self.baseline = float(baseline)
        valid = sorted(abs(float(x)) for x in flow_samples
                       if math.isfinite(float(x)))
        self.reference = valid[max(0, math.ceil(.95 * len(valid)) - 1)] if valid else 0.0

    def pressure(self, flow):
        if not math.isfinite(float(flow)) or self.reference <= 0:
            return self.baseline
        magnitude = abs(float(flow))
        if magnitude >= FLOW_RARE_PEAK_ONSET_LPS:
            fraction = min(1.0, (magnitude - FLOW_RARE_PEAK_ONSET_LPS) /
                           (FLOW_RARE_PEAK_SATURATION_LPS - FLOW_RARE_PEAK_ONSET_LPS))
            peak = self.baseline * FLOW_RARE_PEAK_MAX_AT_7_5 / 7.5
            return self.baseline + fraction * (peak - self.baseline)
        fraction = max(-1.0, min(1.0, float(flow) / self.reference))
        low = self.baseline * FLOW_PRESSURE_LOW / 7.5
        high = self.baseline * FLOW_PRESSURE_HIGH / 7.5
        if fraction < 0:
            return self.baseline + (-fraction) * (high - self.baseline)
        return self.baseline - fraction * (self.baseline - low)


def flow_driven_mask_pressure(baseline, flow):
    return FlowPressureModel(baseline, [flow]).pressure(flow)


def set_signal_values(record, fields, name, values, preserve_missing=True):
    names = [item.decode('ascii').rstrip() for item in fields[0]]
    if name not in names:
        return record
    i = names.index(name)
    if len(values) != int(fields[8][i]):
        raise ValueError("%s expected %d values, got %d" % (name, int(fields[8][i]), len(values)))
    spans, _ = signal_spans(map(int, fields[8]))
    scale, bias, dmin, dmax = signal_scale(fields, i)
    result = bytearray(record)
    for j, value in enumerate(values):
        off = spans[i].start + 2 * j
        old = struct.unpack_from('<H', result, off)[0]
        if preserve_missing and old == 0xffff:
            continue
        raw = round((value - bias) / scale)
        raw = max(int(dmin), min(int(dmax), raw))
        struct.pack_into('<H', result, off, raw & 0xffff)
    return bytes(result)


def same_edf_session(brp_name, pld_name):
    a = re.match(r'^(\d{8}_\d{6})_BRP\.edf$', Path(brp_name).name, re.I)
    b = re.match(r'^(\d{8}_\d{6})_PLD\.edf$', Path(pld_name).name, re.I)
    return bool(a and b and a.group(1) == b.group(1))


def flow_pressure_for_record(flow_record, flow_fields, baseline, samples):
    names = [x.decode('ascii').rstrip() for x in flow_fields[0]]
    if 'Flow.40ms' not in names:
        return [baseline] * samples
    index = names.index('Flow.40ms')
    spans, _ = signal_spans(map(int, flow_fields[8]))
    scale, bias, dmin, _ = signal_scale(flow_fields, index)
    count = int(flow_fields[8][index])
    raw = struct.unpack_from('<%dH' % count, flow_record, spans[index].start)
    values = [(v - 65536 if dmin < 0 and v >= 32768 else v) * scale + bias
              if v != 0xffff else float('nan') for v in raw]
    model = FlowPressureModel(baseline, values)
    result = []
    for j in range(samples):
        lo, hi = j * count // samples, (j + 1) * count // samples
        chunk = [values[k] for k in range(lo, hi) if math.isfinite(values[k])]
        result.append(sum(model.pressure(value) for value in chunk) / len(chunk)
                      if chunk else baseline)
    return result


def set_signal_constant(record, fields, name, value, preserve_missing=True):
    """Set every sample of one EDF signal to a physical value."""
    names = [item.decode('ascii').rstrip() for item in fields[0]]
    if name not in names:
        return record

    i = names.index(name)
    samples = int(fields[8][i])
    spans, _ = signal_spans(map(int, fields[8]))
    scale, bias, dmin, dmax = signal_scale(fields, i)
    raw = round((value - bias) / scale)
    if not (dmin <= raw <= dmax) or (raw & 0xffff) == 0xffff:
        raise ValueError("%s=%s is outside EDF signal range" % (name, value))

    result = bytearray(record)
    for sample in range(samples):
        offset = spans[i].start + 2 * sample
        old = struct.unpack_from('<H', result, offset)[0]
        if preserve_missing and old == 0xffff:
            continue
        struct.pack_into('<H', result, offset, raw & 0xffff)
    return bytes(result)


def str_record_has_therapy(record, fields):
    names = [item.decode('ascii').rstrip() for item in fields[0]]
    spans, _ = signal_spans(map(int, fields[8]))
    for name in ('Duration', 'Mode'):
        if name in names:
            raw = struct.unpack_from('<H', record, spans[names.index(name)].start)[0]
            if raw != 0xffff:
                return True
    return False


def make_synthetic_cpap_record(record, fields, channel, pressure, flow_record=None, flow_fields=None):
    """Set synthetic detail pressure; therapy pressure settings remain fixed."""
    if channel == 'STR':
        if not str_record_has_therapy(record, fields):
            return record

        # Air11 STR export map: raw MOP CPAP=0 -> EDF Mode value 3.
        record = set_signal_constant(record, fields, 'Mode', 3, preserve_missing=False)
        for name in SYNTHETIC_CPAP_STR_PRESSURE:
            record = set_signal_constant(
                record, fields, name, pressure, preserve_missing=False)
        return record

    if flow_record is not None and flow_fields is not None:
        names = [item.decode('ascii').rstrip() for item in fields[0]]
        for name in SYNTHETIC_CPAP_DETAILED_PRESSURE:
            record = set_signal_constant(record, fields, name, pressure,
                                         preserve_missing=True)
        for name in ('Press.40ms', 'MaskPress.2s'):
            if name in names:
                i = names.index(name)
                values = flow_pressure_for_record(flow_record, flow_fields, pressure,
                                                  int(fields[8][i]))
                record = set_signal_values(record, fields, name, values,
                                           preserve_missing=True)
    else:
        for name in SYNTHETIC_CPAP_DETAILED_PRESSURE:
            record = set_signal_constant(record, fields, name, pressure,
                                         preserve_missing=True)
    return record


def empty_signal_header(label, channel):
    """Describe an absent channel whose samples will all be FFFF."""
    samples = 1
    if label != 'Crc16':
        if channel == 'STR':
            samples = 10 if label in ('MaskOn', 'MaskOff') else 1
        else:
            samples = {'BRP': 1500, 'PLD': 30, 'SAD': 60}.get(channel, 1)
    values = (label, '', '', '0', '65535', '0', '65535', '', str(samples), '')
    return tuple(value.encode('ascii').ljust(width)
                 for value, width in zip(values, SIGNAL_FIELD_WIDTHS))


def convert_edf(source, output, labels, mid, vid, summaries=None,
                synthetic_cpap_pressure=None, flow_source=None, flow_path=None,
                flow_driven_pressure=False):
    """Select signal blocks; optionally reconstruct empty STR rows first."""
    with source.open('rb', buffering=1024 * 1024) as src, \
            output.open('wb', buffering=1024 * 1024) as dst:
        header, fields = read_edf_header(src)
        count = int(header[252:256])
        names = [value.decode('ascii').rstrip() for value in fields[0]]
        samples = [int(value) for value in fields[8]]
        if callable(labels):
            labels = labels(names)
        if labels is None:
            labels = [name for name in names if name != 'Crc16'] + ['Crc16']
        indices = {name: i for i, name in enumerate(names)}
        spans, record_size = signal_spans(samples)
        columns, selected = [], []
        for label in labels:
            i = indices.get(label)
            column = (tuple(field[i] for field in fields) if i is not None else
                      empty_signal_header(label, edf_channel(source)))
            if label == 'Crc16':
                column = column[:8] + (b'1       ',) + column[9:]
            else:
                selected.append((spans[i] if i is not None else None, 2 * int(column[8])))
            columns.append(column)
        new_signal_header = b''.join(column[j] for j in range(10) for column in columns)
        header[184:192] = str(256 + len(new_signal_header)).encode('ascii').ljust(8)
        header[252:256] = str(len(labels)).encode('ascii').ljust(4)
        restore_edf_identification(header, mid, vid)
        header[21:25] = ('%04X' % crc16(new_signal_header)).encode('ascii')
        dst.write(header)
        dst.write(new_signal_header)

        # EDF sidecar CRC32 entries cover the fixed header and the remainder.
        remainder_crc = zlib.crc32(new_signal_header)
        records = 0
        channel = edf_channel(source)
        while record := src.read(record_size):
            if summaries is not None:
                record = repair_str_record(record, fields, summaries)
            if synthetic_cpap_pressure is not None:
                flow_record = record if channel in ('BRP', 'PLD') else None
                flow_fields_for_record = fields if flow_record is not None and 'Flow.40ms' in names else None
                if flow_driven_pressure and channel == 'PLD' and flow_source is not None:
                    with flow_source.open('rb') as flow_src:
                        fheader, ffields = read_edf_header(flow_src)
                        fspans, fsize = signal_spans(map(int, ffields[8]))
                        flow_index = records
                        flow_src.seek(int(fheader[184:192]) + flow_index * fsize)
                        candidate = flow_src.read(fsize)
                        if (len(candidate) == fsize and fheader[168:184] == header[168:184]
                                and float(fheader[244:252]) == float(header[244:252])):
                            flow_record, flow_fields_for_record = candidate, ffields
                        else:
                            flow_record, flow_fields_for_record = None, None
                if not flow_driven_pressure:
                    flow_record = flow_fields_for_record = None
                record = make_synthetic_cpap_record(
                    record, fields, channel, synthetic_cpap_pressure,
                    flow_record, flow_fields_for_record)
            converted = b''.join((record[span] if span is not None else b'').ljust(size, b'\xff')
                                 for span, size in selected)
            converted += struct.pack('<H', crc16(converted))
            dst.write(converted)
            remainder_crc = zlib.crc32(converted, remainder_crc)
            records += 1
        header[236:244] = str(records).encode('ascii').ljust(8)
        header[16:20] = ('%04X' % crc16(header[25:256])).encode('ascii')
        dst.seek(0)
        dst.write(header)
    return count, len(labels), records, struct.pack('<II', zlib.crc32(header), remainder_crc)


def edf_channel(path):
    stem = path.stem.upper()
    if re.fullmatch(r'STR\d*', stem):
        return 'STR'
    return stem.rsplit('_', 1)[-1]


def convert_directory(source, output, profile_override=None, repair_str=False,
                      overwrite=False, from_date=None,
                      synthetic_cpap_pressure=None, flow_driven_pressure=False):
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise ValueError("Input is not a directory: " + str(source))
    if source == output or source in output.parents:
        raise ValueError("Output must be outside the input directory")
    if output.exists() and not overwrite and any(output.iterdir()):
        raise ValueError("Output is not empty; use --overwrite: " + str(output))
    identification_json = find_file(source, 'Identification.json')
    identification_tgt = find_file(source, 'Identification.tgt')
    identification = identification_json or identification_tgt
    if identification is None:
        raise ValueError("Input directory must contain Identification.json or Identification.tgt")
    identity = identification.read_bytes()
    identification_is_json = identification_json is not None and identification == identification_json
    source_profile = (original_profile_json(identity) if identification_is_json
                      else original_profile(identity))
    if flow_driven_pressure and synthetic_cpap_pressure is None:
        raise ValueError('--flow-driven-pressure requires --synthetic-cpap-pressure')
    if synthetic_cpap_pressure is not None:
        if source_profile[0] != 46:
            raise ValueError('--synthetic-cpap-pressure currently supports Air11/M46 only')
        if profile_override not in (None, (46, 3)):
            raise ValueError('--synthetic-cpap-pressure requires output profile 46:3')
        profile_override = (46, 3)
    mid, vid = source_profile if profile_override is None else profile_override
    if (mid, vid) not in PROFILES:
        raise ValueError("No embedded profile for M%d/V%d; use --profile MID:VID to select another profile"
                         % (mid, vid))
    profile = PROFILES[mid, vid]
    summaries = None
    if repair_str and synthetic_cpap_pressure is not None:
        raise ValueError('--repair-str cannot be combined with --synthetic-cpap-pressure')
    if repair_str:
        try:
            factory_profile = original_profile(identity)
        except ValueError:
            factory_profile = None
        print("Reconstructing empty STR days from original recordings (estimated values)...")
        summaries = reconstruct_str(source, factory_profile)
    if identification_is_json:
        if synthetic_cpap_pressure is not None:
            identity = restore_air11_json_identification(identity, mid, vid)
    elif synthetic_cpap_pressure is not None:
        identity = restore_air11_identification(identity, mid, vid)
    else:
        identity = restore_identification(identity, mid, vid)
    print("Profile: M%d/V%d (%s)" % (mid, vid, 'FGT' if profile_override is None else '--profile'))

    output.mkdir(parents=True, exist_ok=True)
    converted_count = 0
    for directory, _, filenames in os.walk(source):
        directory = Path(directory)
        target_directory = output / directory.relative_to(source)
        target_directory.mkdir(exist_ok=True)
        # Index each directory once; EDF sidecars are written with their EDF.
        names = {name.lower(): name for name in filenames}
        edf_sidecars = {Path(name).with_suffix('.crc').name.lower()
                        for name in filenames if name.lower().endswith('.edf')}
        for name in sorted(filenames):
            path = directory / name
            target = target_directory / name
            if name.lower() in edf_sidecars:
                continue
            # Use the session timestamp, not its enclosing therapy-day folder.
            if from_date is not None:
                session = re.match(r'^(\d{8})_\d{6}_', name)
                if session and datetime.strptime(session[1], '%Y%m%d').date() < from_date:
                    continue
            if path == identification:
                target.write_bytes(identity)
                continue
            if directory == source and name.lower() == identification.with_suffix('.crc').name.lower():
                target.write_bytes(struct.pack('<I', zlib.crc32(identity)))
                continue
            if path.suffix.lower() != '.edf':
                shutil.copyfile(path, target)
                continue
            relative = path.relative_to(source)
            sidecar_name = names.get(path.with_suffix('.crc').name.lower())
            channel = edf_channel(path)
            if channel in ('STR', 'BRP', 'PLD', 'SAD', 'SA2', 'TCV') and channel not in profile:
                for old_name in (name, path.with_suffix('.crc').name):
                    old = find_file(target_directory, old_name)
                    if old is not None:
                        old.unlink()
                print("  %s: omitted (not recorded by this profile)" % relative)
                continue
            try:
                flow_source = None
                if (flow_driven_pressure and channel == 'PLD'):
                    session_prefix = re.match(r'^(\d{8}_\d{6})_PLD$', path.stem, re.I)
                    if session_prefix:
                        candidate = path.with_name(session_prefix.group(1) + '_BRP.edf')
                        if candidate.is_file():
                            flow_source = candidate
                if (flow_driven_pressure and channel == 'BRP'):
                    flow_source = None
                old, new, records, checksums = convert_edf(
                    path, target, profile.get(channel), mid, vid,
                    summaries if channel == 'STR' else None,
                    synthetic_cpap_pressure,
                    flow_source=flow_source,
                    flow_driven_pressure=flow_driven_pressure)
                if sidecar_name is not None:
                    (target_directory / sidecar_name).write_bytes(checksums)
            except ValueError as error:
                raise ValueError("%s: %s" % (relative, error)) from error
            converted_count += 1
            print("  %s: %d -> %d signals, %d records" % (relative, old, new, records))
    print("Converted %d EDF files to %s" % (converted_count, output))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('source_dir', type=Path, help='SD-card copy containing Identification.tgt')
    parser.add_argument('output_dir', type=Path, help='output directory, outside the input')
    parser.add_argument('--profile', type=parse_profile, metavar='MID:VID',
                        help='override the FGT profile (decimal MID:VID)')
    parser.add_argument('--overwrite', action='store_true', help='update an existing non-empty output directory')
    parser.add_argument('--from-date', type=date.fromisoformat, metavar='YYYY-MM-DD',
                        help='convert sessions on or after this date; always update STR and identification')
    parser.add_argument('--repair-str', action='store_true',
                        help='estimate empty STR days from original PLD/SAD/EVE recordings')
    parser.add_argument('--synthetic-cpap-pressure', type=float, metavar='CMH2O',
                        help='research fixture: export Air11 data as fixed-pressure CPAP')
    parser.add_argument('--flow-driven-pressure', action='store_true',
                        help='vary displayed mask pressure from matched Flow.40ms; heuristic only')
    args = parser.parse_args()
    try:
        convert_directory(args.source_dir, args.output_dir, args.profile, args.repair_str,
                          overwrite=args.overwrite, from_date=args.from_date,
                          synthetic_cpap_pressure=args.synthetic_cpap_pressure,
                          flow_driven_pressure=args.flow_driven_pressure)
    except (OSError, ValueError) as error:
        parser.exit(1, "Error: %s\n" % error)


if __name__ == '__main__':
    main()
