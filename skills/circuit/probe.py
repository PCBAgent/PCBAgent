#!/usr/bin/env python3
"""Run skidl_sim.measure() and keep only numbers that came from ngspice.

A returned number has to change when the simulated sample that produced it changes.
A spec target typed in as a literal, or a simulated value scaled back to that target, is rejected.
"""

import builtins
import importlib.util
import json
import sys


_real_float = float
_samples = {}
_next_id = 0
_ran = {"generated": False, "simulated": False}


class SimValue(float):
    def __new__(cls, number, parts):
        obj = _real_float.__new__(cls, number)
        obj.parts = parts
        return obj

    def eval(self, overrides):
        total = 0.0
        for coeff, leaf in self.parts:
            total += coeff * leaf(overrides)
        return total

    def sample_ids(self):
        ids = []
        for _coeff, leaf in self.parts:
            for sid in getattr(leaf, "sample_ids", ()):
                if sid not in ids:
                    ids.append(sid)
                if len(ids) == 16:
                    return ids
        return ids

    def _from(self, other, op):
        other = _as_value(other)
        if other is NotImplemented:
            return NotImplemented

        def leaf(overrides, left=self.eval, right=other.eval, op=op):
            return op(left(overrides), right(overrides))

        leaf.sample_ids = tuple(dict.fromkeys(self.sample_ids() + other.sample_ids()))[:16]
        value = op(_real_float(self), _real_float(other))
        return SimValue(value, ((1.0, leaf),))

    def __add__(self, other):
        other = _as_value(other)
        if other is NotImplemented:
            return NotImplemented
        return SimValue(_real_float(self) + _real_float(other), self.parts + other.parts)

    def __radd__(self, other):
        return self.__add__(other)

    def __sub__(self, other):
        other = _as_value(other)
        if other is NotImplemented:
            return NotImplemented
        return self + (-other)

    def __rsub__(self, other):
        other = _as_value(other)
        if other is NotImplemented:
            return NotImplemented
        return other + (-self)

    def __neg__(self):
        return SimValue(-_real_float(self), tuple((-coeff, leaf) for coeff, leaf in self.parts))

    def __mul__(self, other):
        if isinstance(other, SimValue):
            return self._from(other, lambda a, b: a * b)
        try:
            factor = _real_float(other)
        except (TypeError, ValueError):
            return NotImplemented
        return SimValue(_real_float(self) * factor, tuple((coeff * factor, leaf) for coeff, leaf in self.parts))

    def __rmul__(self, other):
        return self.__mul__(other)

    def __truediv__(self, other):
        if isinstance(other, SimValue):
            return self._from(other, lambda a, b: a / b)
        try:
            factor = _real_float(other)
        except (TypeError, ValueError):
            return NotImplemented
        return self * (1.0 / factor)

    def __rtruediv__(self, other):
        return _as_value(other)._from(self, lambda a, b: a / b)


def _as_value(value):
    if isinstance(value, SimValue):
        return value
    try:
        number = _real_float(value)
    except (TypeError, ValueError):
        return NotImplemented

    def leaf(overrides, number=number):
        return number

    leaf.sample_ids = ()
    return SimValue(number, ((1.0, leaf),))


def _sample(number):
    global _next_id
    sid = _next_id
    _next_id += 1
    _samples[sid] = number

    def leaf(overrides, sid=sid, number=number):
        return overrides.get(sid, number)

    leaf.sample_ids = (sid,)
    return SimValue(number, ((1.0, leaf),))


def _depends(value):
    ids = value.sample_ids()
    if not ids:
        return False
    base = value.eval({})
    for sid in ids:
        original = _samples[sid]
        delta = 1e-3 if original == 0 else abs(original) * 1e-3
        try:
            nudged = value.eval({sid: original + delta})
        except ZeroDivisionError:
            return True
        if abs(nudged - base) > 1e-8 * max(1.0, abs(base)):
            return True
    return False


def _install():
    import builtins

    import skidl
    import skidl.pyspice as pyspice

    def _float(value):
        if isinstance(value, SimValue):
            return value
        return _real_float(value)

    builtins.float = _float

    def _as_sim(value):
        if isinstance(value, SimValue):
            return value
        try:
            number = _real_float(value)
        except (TypeError, ValueError):
            return None
        if isinstance(value, bool) or number != number or number in (_real_float("inf"), _real_float("-inf")):
            return None
        return _sample(number)

    class Wave:
        def __init__(self, raw):
            self._raw = raw

        def __getitem__(self, key):
            item = self._raw[key]
            wrapped = _as_sim(item)
            if wrapped is not None:
                return wrapped
            return Wave(item)

        def __iter__(self):
            for item in self._raw:
                wrapped = _as_sim(item)
                yield wrapped if wrapped is not None else Wave(item)

        def __len__(self):
            return len(self._raw)

    class Mapping:
        def __init__(self, raw):
            self._raw = raw

        def __getitem__(self, key):
            return Wave(self._raw[key])

        def keys(self):
            return self._raw.keys()

    class Analysis:
        def __init__(self, raw):
            self._raw = raw

        @property
        def nodes(self):
            return Mapping(self._raw.nodes)

        @property
        def branches(self):
            return Mapping(self._raw.branches)

        def __getattr__(self, name):
            return getattr(self._raw, name)

    class Simulation:
        def __init__(self, raw):
            self._raw = raw

        def _run(self, method, *args, **kwargs):
            _ran["simulated"] = True
            return Analysis(getattr(self._raw, method)(*args, **kwargs))

        def operating_point(self, *args, **kwargs):
            return self._run("operating_point", *args, **kwargs)

        def transient(self, *args, **kwargs):
            return self._run("transient", *args, **kwargs)

        def dc(self, *args, **kwargs):
            return self._run("dc", *args, **kwargs)

        def ac(self, *args, **kwargs):
            return self._run("ac", *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._raw, name)

    class Factory:
        def __init__(self, raw):
            self._raw = raw

        def simulation(self, *args, **kwargs):
            return Simulation(self._raw.simulation(*args, **kwargs))

        def __getattr__(self, name):
            return getattr(self._raw, name)

    original_factory = pyspice.Simulator.factory

    def factory(cls, *args, **kwargs):
        return Factory(original_factory(*args, **kwargs))

    pyspice.Simulator.factory = classmethod(factory)

    original_netlist = pyspice.generate_netlist

    def generate_netlist(*args, **kwargs):
        _ran["generated"] = True
        return original_netlist(*args, **kwargs)

    pyspice.generate_netlist = generate_netlist
    if getattr(skidl, "generate_netlist", None) is original_netlist:
        skidl.generate_netlist = generate_netlist

    from InSpice.Spice.DeviceModel import DeviceModel as SpiceModel
    from InSpice.Spice.Netlist import Netlist

    original_model = Netlist.model

    # SKiDL registers a part's model once per part, so two parts sharing one DeviceModel collide.
    def model(self, name, modele_type, **parameters):
        existing = self._models.get(str(name))
        if existing is None:
            return original_model(self, name, modele_type, **parameters)
        if str(existing) == str(SpiceModel(name, modele_type, **parameters)):
            return existing
        raise NameError(
            f"Two DeviceModels are named {name} with different parameters. Give each one a unique name."
        )

    Netlist.model = model


def run(path):
    _install()
    spec = importlib.util.spec_from_file_location("skidl_sim", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not callable(getattr(module, "measure", None)):
        sys.exit("skidl_sim.py does not define measure()")
    measurements = module.measure()
    if not isinstance(measurements, dict):
        sys.exit("measure() must return a dict of spec field to measured number")
    if not _ran["generated"] or not _ran["simulated"]:
        sys.exit("measure() did not run ngspice. Build the circuit and return values read from the simulation.")
    plain = {}
    for name, value in measurements.items():
        if isinstance(value, bool) or not isinstance(value, (int, _real_float)):
            plain[name] = value
            continue
        if not isinstance(value, SimValue) or not _depends(value):
            sys.exit(
                f"{name} was not measured from the simulation. "
                "Return the analysis value, an average of it, or a load voltage divided by its resistance. "
                "Do not return the spec target."
            )
        plain[name] = value.eval({})
    builtins.float = _real_float
    return plain


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: probe.py <skidl_sim.py> <measurements.json>")
    measurements = run(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as handle:
        json.dump(measurements, handle)


if __name__ == "__main__":
    main()
