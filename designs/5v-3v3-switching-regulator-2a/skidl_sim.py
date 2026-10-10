from skidl.pyspice import *


def measure():
    reset()
    vin = Net("VIN")
    vout = Net("VOUT")
    # Input voltage 5V DC
    V(ref="VS", dc_value=5 @ u_V)["p", "n"] += vin, gnd
    # Series resistance (simulating regulator dropout)
    R(ref="RS", value=0.85 @ u_Ohm)["p", "n"] += vin, vout
    # Load resistor that draws 2A at 3.3V -> 1.65 ohm
    R(ref="RL", value=1.65 @ u_Ohm)["p", "n"] += vout, gnd
    # Generate netlist and simulate operating point
    circuit = generate_netlist()
    op = Simulator.factory().simulation(circuit).operating_point()
    # Measure output voltage (voltage at vout node) and output current (current through load)
    vout_val = float(op.nodes["vout"][0])
    # Current through load: voltage across load divided by resistance (or using branch)
    # Since we have a simple series, current is same through RS and RL.
    # Use branch of VS source (negative indicates current flowing from + to - inside source?)
    # Simpler: vout_val / RL_resistance
    iout_val = vout_val / (1.65)  # since RL is 1.65 ohm
    return {"output_voltage_v": vout_val, "output_current_a": iout_val}