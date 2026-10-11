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

c1 = Part("Device", "C", ref="C1", value="10uF", footprint="Capacitor_SMD:C_0402_1005Metric")
c2 = Part("Device", "C", ref="C2", value="100nF", footprint="Capacitor_SMD:C_0402_1005Metric")
c3 = Part("Device", "C", ref="C3", value="22uF", footprint="Capacitor_SMD:C_0603_1608Metric")
c4 = Part("Device", "C", ref="C4", value="100nF", footprint="Capacitor_SMD:C_0402_1005Metric")
r1 = Part("Device", "R", ref="R1", value="10k", footprint="Resistor_SMD:R_0603_1608Metric")
r2 = Part("Device", "R", ref="R2", value="10k", footprint="Resistor_SMD:R_0603_1608Metric")
r3 = Part("Device", "R", ref="R3", value="33", footprint="Resistor_SMD:R_0402_1005Metric")
u1 = Part("Regulator_Linear", "AMS1117-3.3", ref="U1", value="AMS1117-3.3", footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2")
u2 = Part("Amplifier_Operational", "LM358", ref="U2", value="LM358", footprint="Package_SO:SOIC-8_3.9x4.9mm_P1.27mm")

c1[1] += vin
c1[2] += gnd
c2[1] += vin
c2[2] += gnd
c3[1] += ldo_out
c3[2] += gnd
c4[1] += ldo_out
c4[2] += gnd
r1[1] += ldo_out
r1[2] += div_mid
r2[1] += div_mid
r2[2] += gnd
r3[1] += vout
r3[2] += gnd

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

ERC()
generate_netlist(file_="board.net")
