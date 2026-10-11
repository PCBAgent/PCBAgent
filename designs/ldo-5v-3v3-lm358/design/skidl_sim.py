from skidl.pyspice import *


def measure():
    reset()
    vin = Net("VIN")
    vout = Net("VOUT")
    ldo_out = Net("LDO_OUT")
    gnd = Net("GND")

    # Input voltage source
    V(ref="VIN", dc_value=5 @ u_V)["p", "n"] += vin, gnd

    # Input capacitor
    C(ref="CIN", value=10 @ u_uF)["p", "n"] += vin, gnd

    # Regulator decoupling capacitor (input side)
    C(ref="CIN_DEC", value=100 @ u_nF)["p", "n"] += vin, gnd

    # LDO: we model as an ideal voltage source of 3.3V from LDO_OUT to GND
    V(ref="LDO_REG", dc_value=3.3 @ u_V)["p", "n"] += ldo_out, gnd

    # Connect LDO input to VIN (for completeness)
    ldo_in = Net("LDO_IN")
    ldo_in += vin

    # Output capacitor
    C(ref="COUT", value=22 @ u_uF)["p", "n"] += ldo_out, gnd

    # LM358 power rails
    vcc_lm358 = Net("LM358_VCC")
    gnd_lm358 = Net("LM358_GND")
    vcc_lm358 += ldo_out  # LM358 Vcc connected to LDO output
    gnd_lm358 += gnd

    # LM358 decoupling capacitor
    C(ref="C_LM358_DEC", value=100 @ u_nF)["p", "n"] += vcc_lm358, gnd_lm358

    # Divider for LM358 non-inverting input: two 10k resistors from ldo_out to gnd
    rtop = R(ref="RTENTOP", value=10 @ u_kOhm)
    rtop["p", "n"] += ldo_out, Net("DIV_MID")
    rbottom = R(ref="RTENBOT", value=10 @ u_kOhm)
    rbottom["p", "n"] += Net("DIV_MID"), gnd

    # LM358 opamp (unity gain buffer) using a high-gain VCVS
    e_lm358 = E(ref="LM358", gain=1000)
    e_lm358["ip", "in", "op", "on"] += Net("DIV_MID"), Net("LM358_OUT"), Net("LM358_OUT"), gnd

    # Load
    R(ref="RL", value=33 @ u_Ohm)["p", "n"] += vout, gnd

    # Connect the LM358 output to VOUT (the board output)
    vout += Net("LM358_OUT")

    # Now, we need to measure the output voltage and current.
    # We'll run an operating point analysis.
    circuit = generate_netlist()
    op = Simulator.factory().simulation(circuit).operating_point()
    vout_volt = float(op.nodes["vout"][0])
    # Current through RL: voltage across RL divided by resistance
    i_out = vout_volt / 33.0  # in Amps
    return {
        "output_voltage_v": vout_volt,
        "output_current_a": i_out
    }