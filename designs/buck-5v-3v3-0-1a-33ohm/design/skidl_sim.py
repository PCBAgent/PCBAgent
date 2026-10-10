from skidl.pyspice import *


def measure():
    reset()
    vin = Net("VIN")
    vout = Net("VOUT")
    # Input voltage 5V
    V(ref="VS", dc_value=5 @ u_V)["p", "n"] += vin, gnd
    # Resistor divider: R1 from vin to vout, R2 from vout to gnd
    R1 = R(value=10 @ u_Ohm)
    R1["p", "n"] += vin, vout
    R2 = R(value=47.13 @ u_Ohm)
    R2["p", "n"] += vout, gnd
    # Load: 33 ohm from vout to gnd, but we insert a zero-volt source to measure current
    Rload = R(value=33 @ u_Ohm)
    Vref = V(ref="VMEASURE", dc_value=0 @ u_V)
    # Connect: vout -- Rload -- node_load -- Vref -- gnd
    node_load = Net("LOAD")
    Rload["p", "n"] += vout, node_load
    Vref["p", "n"] += node_load, gnd
    # Operating point simulation
    op = Simulator.factory().simulation(generate_netlist()).operating_point()
    # Measure output voltage at vout
    vout_val = float(op.nodes["vout"][0])
    # Measure current through Vref (which is the same as load current)
    # The branch name is lowercased: "vmeasure"
    i_load = float(op.branches["vmeasure"][0])
    return {"output_voltage_v": vout_val, "output_current_a": i_load}