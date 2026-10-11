from skidl.pyspice import *


def measure():
    reset()
    vin = Net("VIN")
    vout = Net("VOUT")
    # Input voltage source
    V(ref="VS", dc_value=5 @ u_V)["p", "n"] += vin, gnd
    # Input capacitor
    C(value=10 @ u_uF)["p", "n"] += vin, gnd
    # LDO as a voltage source (fixed 3.3V from output to ground)
    V(ref="VLDO", dc_value=3.3 @ u_V)["p", "n"] += vout, gnd
    # Output capacitor
    C(value=22 @ u_uF)["p", "n"] += vout, gnd
    # Load resistor
    R(value=33 @ u_Ohm)["p", "n"] += vout, gnd
    # Generate netlist and simulate
    circuit = generate_netlist()
    analysis = Simulator.factory().simulation(circuit).operating_point()
    # Measure output voltage
    vout_voltage = analysis.nodes["vout"][0]
    # Measure load current: voltage across resistor divided by resistance
    # Since resistor is between vout and gnd, the current is vout_voltage / 33.0
    i_load = vout_voltage / 33.0
    return {
        "output_voltage_v": float(vout_voltage),
        "output_current_a": float(i_load)
    }