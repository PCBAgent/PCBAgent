from skidl.pyspice import *


def measure():
    reset()
    vin = Net("VIN")
    vout = Net("VOUT")
    # Supply voltage
    V(ref="VS", dc_value=5 @ u_V)["p", "n"] += vin, gnd
    # Resistor divider: R1 = 10 ohm, R2 = 47 ohm
    R(value=10 @ u_Ohm)["p", "n"] += vin, vout
    R(value=47 @ u_Ohm)["p", "n"] += vout, gnd
    # Load resistor: 33 ohm
    R(value=33 @ u_Ohm)["p", "n"] += vout, gnd
    circuit = generate_netlist()
    op = Simulator.factory().simulation(circuit).operating_point()
    vout_voltage = float(op.nodes["vout"][0])
    # Current through load: Vout / R_load
    load_current = vout_voltage / (33 @ u_Ohm)
    return {
        "output_voltage_v": vout_voltage,
        "output_current_a": float(load_current)
    }