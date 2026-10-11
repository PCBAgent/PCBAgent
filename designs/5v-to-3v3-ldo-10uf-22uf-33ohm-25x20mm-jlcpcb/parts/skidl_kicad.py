from skidl import *

set_default_tool(KICAD)

# Nets
vin = Net("VIN")
vout = Net("VOUT")
gnd = Net("GND")

# Parts from parts.json
# C1: 10uF input capacitor
c1 = Part("Device", "C", value="10uF 6.3V X5R ±20% 0402 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS CL05A106MQ5NUNC", footprint="Capacitor_SMD:C_0402_1005Metric")
# C2: 22uF output capacitor
c2 = Part("Device", "C", value="22uF 6.3V X5R ±20% 0603 Multilayer Ceramic Capacitors MLCC - SMD/SMT ROHS CL10A226MQ8NRNC", footprint="Capacitor_SMD:C_0603_1608Metric")
# R1: 33 ohm load resistor
r1 = Part("Device", "R", value="-55℃~+155℃ 33Ω 50V 62.5mW Thick Film Resistor ±1% ±100ppm/℃ 0402 Chip Resistor - Surface Mount ROHS 0402WGF330JTCE", footprint="Resistor_SMD:R_0402_1005Metric")
# U1: AMS1117-3.3 regulator
u1 = Part("Regulator_Linear", "AMS1117-3.3", value="-40℃~+125℃ 0.003%Vout 1 1.1V@(800mA) 15V 1A 3.3V 5mA 72dB@(120Hz) Fixed Over Current Protection、Short Circuit Protection、Thermal shutdown Positive SOT-223 Voltage Regulators - Linear, Low Drop Out (LDO) Regulators ROHS AMS1117-3.3", footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2")

# Connections
# C1: between VIN and GND
c1[1] += vin
c1[2] += gnd

# C2: between VOUT and GND
c2[1] += vout
c2[2] += gnd

# R1: between VOUT and GND
r1[1] += vout
r1[2] += gnd

# U1: 
#   Pin 1 (GND) to GND
#   Pin 2 (VO) to VOUT
#   Pin 3 (VI) to VIN
u1[1] += gnd
u1[2] += vout
u1[3] += vin

# ERC and generate netlist
ERC()
generate_netlist(file=open("board.net", "w"))