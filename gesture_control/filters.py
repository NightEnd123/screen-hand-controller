"""One Euro filter (Casiez et al., CHI 2012).

A low-pass filter whose cutoff rises with speed: when the hand is nearly still the
cutoff is low (tremor removed), when it moves fast the cutoff is high (little lag).
"""
import math


def _alpha(cutoff, dt):
    tau = 1.0 / (2 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuro:
    def __init__(self, min_cutoff=1.0, beta=0.0, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.reset()

    def reset(self):
        self.x = None
        self.dx = 0.0
        self.t = None

    def __call__(self, t, x):
        if self.x is None or t <= self.t:
            if self.x is None:
                self.x, self.t = x, t
            return self.x
        dt = t - self.t
        dx = (x - self.x) / dt
        a_d = _alpha(self.d_cutoff, dt)
        self.dx = a_d * dx + (1 - a_d) * self.dx
        cutoff = self.min_cutoff + self.beta * abs(self.dx)
        a = _alpha(cutoff, dt)
        self.x = a * x + (1 - a) * self.x
        self.t = t
        return self.x


class OneEuro2D:
    def __init__(self, **kw):
        self.fx, self.fy = OneEuro(**kw), OneEuro(**kw)

    def reset(self):
        self.fx.reset()
        self.fy.reset()

    def __call__(self, t, p):
        return (self.fx(t, p[0]), self.fy(t, p[1]))
