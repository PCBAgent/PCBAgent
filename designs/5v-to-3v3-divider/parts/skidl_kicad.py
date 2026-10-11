import os
os.environ["KICAD_SYMBOL_DIR"] = "/usr/share/kicad/symbols"
from skidl import *

set_default_tool(KICAD)

# Input voltage net
vin = Net("VIN")
# Output voltage net
vout = Net("VOUT")
# Ground net
gnd = Net("GND")

# Resistor R1: 10 ohm
r1 = Part("Device", "R", value="10 Ω", footprint="Resistor_SMD:R_0402_1005Metric")
r1[1] += vin
r1[2] += vout

# Resistor R2: 47 ohm
r2 = Part("Device", "R", value="47 Ω", footprint="Resistor_SMD:R_0603_1608Metric")
r2[1] += vout
r2[2] += gnd

# Note: The load resistor is not on board, so we do not include it here.

ERC()
generate_netlist(file_="board.net")