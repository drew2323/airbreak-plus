#!/usr/bin/env python3
"""
Convert an airbreak EDF superset SD-card to original ResScan EDF layouts.

Usage: edf_resscan.py INPUT_DIRECTORY OUTPUT_DIRECTORY

"""

import argparse
import binascii
from datetime import date
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

# FGT uses decimal MID/VID; profiles sharing a layout reuse the same lists.
PROFILES = {
    (36, 1): {'STR': STR_M36_V1, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 2): {'STR': STR_M36_V2, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 3): {'STR': STR_M36_V3},
    (36, 5): {'STR': STR_M36_V5, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V27, 'SAD': SAD_M36_V11},
    (36, 7): {'STR': STR_M36_V12, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V11, 'SAD': SAD_M36_V11},
    (36, 9): {'STR': STR_M36_V9, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V27, 'SAD': SAD_M36_V11},
    (36, 11): {'STR': STR_M36_V11, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V11, 'SAD': SAD_M36_V11},
    (36, 12): {'STR': STR_M36_V12, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V11, 'SAD': SAD_M36_V11},
    (36, 19): {'STR': STR_M36_V19, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V19, 'SAD': SAD_M36_V11},
    (36, 25): {'STR': STR_M36_V25, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 26): {'STR': STR_M36_V26, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 27): {'STR': STR_M36_V27, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V27, 'SAD': SAD_M36_V11},
    (36, 28): {'STR': STR_M36_V28, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V11, 'SAD': SAD_M36_V11},
    (36, 34): {'STR': STR_M36_V34, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 35): {'STR': STR_M36_V35},
    (36, 36): {'STR': STR_M36_V36},
    (36, 37): {'STR': STR_M36_V25, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 38): {'STR': STR_M36_V38, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (36, 39): {'STR': STR_M36_V34, 'BRP': BRP_M36_V1, 'PLD': PLD_M36_V1, 'SAD': SAD_M36_V11},
    (40, 41): {'STR': STR_M40_V41, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V41, 'SAD': SAD_M36_V11},
    (40, 43): {'STR': STR_M40_V43, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V41, 'SAD': SAD_M36_V11},
    (40, 44): {'STR': STR_M40_V44, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V44, 'SAD': SAD_M36_V11},
    (40, 45): {'STR': STR_M40_V45, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V41, 'SAD': SAD_M36_V11},
    (40, 46): {'STR': STR_M40_V46, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V44, 'SAD': SAD_M36_V11},
    (40, 48): {'STR': STR_M40_V46, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V44, 'SAD': SAD_M36_V11},
    (40, 49): {'STR': STR_M40_V49, 'BRP': BRP_M36_V11, 'PLD': PLD_M40_V44, 'SAD': SAD_M36_V11},
    (40, 50): {'STR': STR_M40_V50, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V19, 'SAD': SAD_M36_V11},
    (40, 51): {'STR': STR_M40_V50, 'BRP': BRP_M36_V11, 'PLD': PLD_M36_V19, 'SAD': SAD_M36_V11},
}


SIGNAL_FIELD_WIDTHS = (16, 80, 8, 8, 8, 8, 8, 80, 8, 32)


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


def empty_signal_header(label, channel):
    """Describe an absent channel with unitless raw scaling and empty samples."""
    samples = {'BRP': 1500, 'PLD': 30, 'SAD': 60}.get(channel, 1)
    if label in ('MaskOn', 'MaskOff'):
        samples = 10
    elif label == 'Crc16':
        samples = 1
    values = (label, '', '', '-32768', '32767', '-32768', '32767', '', str(samples), '')
    return tuple(value.encode('ascii').ljust(width)
                 for value, width in zip(values, SIGNAL_FIELD_WIDTHS))


def convert_edf(source, output, labels, mid, vid):
    """Select whole signal blocks, preserving metadata and measurement bytes."""
    with source.open('rb', buffering=1024 * 1024) as src, \
            output.open('wb', buffering=1024 * 1024) as dst:
        header = bytearray(src.read(256))
        count = int(header[252:256])
        signal_header = src.read(256 * count)

        # EDF stores each metadata field for all signals before the next field.
        fields = []
        offset = 0
        for width in SIGNAL_FIELD_WIDTHS:
            fields.append([signal_header[offset + i * width:offset + (i + 1) * width]
                           for i in range(count)])
            offset += width * count
        names = [value.decode('ascii').rstrip() for value in fields[0]]
        samples = [int(value) for value in fields[8]]
        if labels is None:
            labels = [name for name in names if name != 'Crc16'] + ['Crc16']

        spans = []
        record_size = 0
        for size in samples:
            spans.append(slice(record_size, record_size + 2 * size))
            record_size += 2 * size
        source_columns = {name: i for i, name in enumerate(names)}
        columns, selected = [], []
        for label in labels:
            index = source_columns.get(label)
            if index is None:
                column = empty_signal_header(label, edf_channel(source))
                span = None
            else:
                column = tuple(field[index] for field in fields)
                span = spans[index]
            columns.append(column)
            selected.append((span, b'\xff\xff' * int(column[8])))

        new_signal_header = b''.join(column[field] for field in range(len(fields)) for column in columns)
        header[184:192] = str(256 + len(new_signal_header)).encode('ascii').ljust(8)
        header[252:256] = str(len(labels)).encode('ascii').ljust(4)
        restore_edf_identification(header, mid, vid)
        header[21:25] = ('%04X' % crc16(new_signal_header)).encode('ascii')
        dst.write(header)
        dst.write(new_signal_header)

        # EDF sidecar CRC32 entries cover the fixed header and the remainder.
        remainder_crc = zlib.crc32(new_signal_header)
        records = 0
        while record := src.read(record_size):
            record = record.ljust(record_size, b'\xff')
            converted = b''.join(record[span] if span is not None else empty
                                 for span, empty in selected[:-1])
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


def convert_directory(source, output, profile_override=None, overwrite=False, from_date=None):
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir():
        raise ValueError("Input is not a directory: " + str(source))
    if source == output or source in output.parents or output in source.parents:
        raise ValueError("Input and output directories must not contain each other")
    if output.exists() and any(output.iterdir()) and not overwrite:
        raise ValueError("Output is not empty; use --overwrite: " + str(output))
    identification = find_file(source, 'Identification.tgt')
    if identification is None:
        raise ValueError("Input directory must contain Identification.tgt")
    identity = identification.read_bytes()
    mid, vid = original_profile(identity) if profile_override is None else profile_override
    if (mid, vid) not in PROFILES:
        raise ValueError("No embedded profile for M%d/V%d" % (mid, vid))
    profile = PROFILES[mid, vid]
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
            session = re.match(r'(\d{8})_\d{6}_', name)
            if from_date and session and session[1] < from_date.strftime('%Y%m%d'):
                continue
            if name.lower() in edf_sidecars:
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
            if channel in ('STR', 'BRP', 'PLD', 'SAD') and channel not in profile:
                print("  %s: omitted (not recorded by this profile)" % relative)
                continue
            try:
                old, new, records, checksums = convert_edf(
                    path, target, profile.get(channel), mid, vid)
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
    args = parser.parse_args()
    try:
        convert_directory(args.source_dir, args.output_dir, args.profile, args.overwrite, args.from_date)
    except (OSError, ValueError) as error:
        parser.exit(1, "Error: %s\n" % error)


if __name__ == '__main__':
    main()
