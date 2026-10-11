from skidl import *

set_default_tool(KICAD)

vin = Net("VIN")
ldo_out = Net("LDO_OUT")
div_mid = Net("DIV_MID")
vout = Net("VOUT")
unused = Net("UNUSED")
gnd = Net("GND")
vin.drive = POWER
gnd.drive = POWER

cin = Part('Device', 'C', ref='CIN', value='10uF 6.3V X5R ±20% 0402 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS CL05A106MQ5NUNC', footprint='Capacitor_SMD:C_0402_1005Metric')
cin_dec = Part('Device', 'C', ref='CIN_DEC', value='100nF 16V X7R ±10% 0402 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS CL05B104KO5NNNC', footprint='Capacitor_SMD:C_0402_1005Metric')
cout = Part('Device', 'C', ref='COUT', value='22uF 6.3V X5R ±20% 0603 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS CL10A226MQ8NRNC', footprint='Capacitor_SMD:C_0603_1608Metric')
c_lm358 = Part('Device', 'C', ref='C_LM358_DEC', value='100nF 16V X7R ±10% 0402 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS CL05B104KO5NNNC', footprint='Capacitor_SMD:C_0402_1005Metric')
rtop = Part('Device', 'R', ref='RTENTOP', value='-55℃~+155℃ 100mW 10kΩ 75V Thick Film Resistor ±1% ±100ppm/℃ 0603 Chip Resistor - Surface Mount ROHS 0603WAF1002T5E', footprint='Resistor_SMD:R_0603_1608Metric')
rbot = Part('Device', 'R', ref='RTENBOT', value='-55℃~+155℃ 100mW 10kΩ 75V Thick Film Resistor ±1% ±100ppm/℃ 0603 Chip Resistor - Surface Mount ROHS 0603WAF1002T5E', footprint='Resistor_SMD:R_0603_1608Metric')
rl = Part('Device', 'R', ref='RL', value='-55℃~+155℃ 33Ω 50V 62.5mW Thick Film Resistor ±1% ±100ppm/℃ 0402 Chip Resistor - Surface Mount ROHS 0402WGF330JTCE', footprint='Resistor_SMD:R_0402_1005Metric')
u1 = Part('Regulator_Linear', 'AMS1117-3.3', ref='U1', value='-40℃~+125℃ 0.003%Vout 1 1.1V@(800mA) 15V 1A 3.3V 5mA 72dB@(120Hz) Fixed Over Current Protection、Short Circuit Protection、Thermal shutdown Positive SOT-223 Voltage Regulators - Linear, Low Drop Out (LDO) Regulators ROHS AMS1117-3.3', footprint='Package_TO_SOT_SMD:SOT-223-3_TabPin2')
u2 = Part('Amplifier_Operational', 'LM358', ref='U2', value='-16V~16V 0℃~+70℃ 2 3V~32V 40mA 45nA 5nA 700uA 70dB 7mV 7uV/℃ Built-in compensation、ESD protection SOIC-8 Operational Amplifier ROHS LM358DR2G', footprint='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm')
tp_vin = Part("Connector", "TestPoint", ref="TP1", value="VIN", footprint="TestPoint:TestPoint_Pad_D1.5mm")
tp_vout = Part("Connector", "TestPoint", ref="TP2", value="VOUT", footprint="TestPoint:TestPoint_Pad_D1.5mm")
tp_gnd = Part("Connector", "TestPoint", ref="TP3", value="GND", footprint="TestPoint:TestPoint_Pad_D1.5mm")

cin[1] += vin
cin[2] += gnd
cin_dec[1] += vin
cin_dec[2] += gnd
cout[1] += ldo_out
cout[2] += gnd
c_lm358[1] += ldo_out
c_lm358[2] += gnd
rtop[1] += ldo_out
rtop[2] += div_mid
rbot[1] += div_mid
rbot[2] += gnd
rl[1] += vout
rl[2] += gnd

u1[1] += gnd
u1[2] += ldo_out
u1[3] += vin

u2[8] += ldo_out
u2[4] += gnd
u2[3] += div_mid
u2[2] += vout
u2[1] += vout
u2[5] += gnd
u2[6] += unused
u2[7] += unused

tp_vin[1] += vin
tp_vout[1] += vout
tp_gnd[1] += gnd

ERC()
generate_netlist(file_="board.net")
