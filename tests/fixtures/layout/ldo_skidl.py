from skidl import *
set_default_tool(KICAD)
j1 = Part("Connector_Generic", "Conn_01x02", ref="J1", footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
j2 = Part("Connector_Generic", "Conn_01x02", ref="J2", footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical")
u1 = Part("Regulator_Linear", "AP2112K-3.3", ref="U1", footprint="Package_TO_SOT_SMD:SOT-23-5")
c1 = Part("Device", "C", ref="C1", value="1uF", footprint="Capacitor_SMD:C_0805_2012Metric")
c2 = Part("Device", "C", ref="C2", value="1uF", footprint="Capacitor_SMD:C_0805_2012Metric")
r1 = Part("Device", "R", ref="R1", value="1k", footprint="Resistor_SMD:R_0805_2012Metric")
d1 = Part("Device", "LED", ref="D1", footprint="LED_SMD:LED_0805_2012Metric")
vin, vout, gnd, led = Net("VIN"), Net("VOUT"), Net("GND"), Net("LED_A")
vin.drive = POWER; gnd.drive = POWER
vin += j1[1], u1["VIN"], u1["EN"], c1[1]
gnd += j1[2], j2[2], u1["GND"], c1[2], c2[2], d1["K"]
vout += j2[1], u1["VOUT"], c2[1], r1[1]
led += r1[2], d1["A"]
u1["NC"] += NC
ERC()
generate_netlist(file_="board.net")
