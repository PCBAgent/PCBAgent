from skidl import *
set_default_tool(KICAD)

# Define nets
vin = Net('5V')
gnd = Net('GND')
fb = Net('FB')
sw = Net('SW')  # We hope this pin exists

# Instantiate parts from parts.json
u1 = Part('Regulator_Switching', 'XL1509-ADJ', footprint='Package_SO:SOIC-8_3.9x4.9mm_P1.27mm')
u1.ref = 'U1'
r1 = Part('Device', 'R', footprint='Resistor_SMD:R_0402_1005Metric')
r1.ref = 'R1'
r2 = Part('Device', 'R', footprint='Resistor_SMD:R_0603_1608Metric')
r2.ref = 'R2'

# Print the pins of the regulator to see what we have
print("Regulator pins:", u1.pins)

# Connections
# Regulator
u1['VIN'] += vin
u1['GND'] += gnd
# Try to connect FB and SW if they exist
if 'FB' in u1.pins:
    u1['FB'] += fb
else:
    print("Warning: FB pin not found")
if 'SW' in u1.pins:
    u1['SW'] += sw
else:
    print("Warning: SW pin not found")

# Resistors
r1[1] += vin
r1[2] += gnd
r2[1] += vin
r2[2] += gnd

# Optional: add a load? Not on board, so skip.

# Check for electrical rule violations
ERC()

# Generate netlist
generate_netlist(file_='board.net')