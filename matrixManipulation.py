#!/usr/bin/env python3

from copy import deepcopy
from dataclasses import dataclass, field
from fractions import Fraction


# =========================
# Domain handling
# =========================

class DomainError(Exception):
    pass


class Domain:

    def __init__(self, name, modulus=None):
        self.name = name
        self.modulus = modulus

    @staticmethod
    def parse(domain_str):
        s = domain_str.strip().upper()

        if s in ["R", "Q", "Z", "N"]:
            return Domain(s)

        if s.startswith("Z_"):
            n = int(s[2:])
            return Domain("Z_n", n)

        raise ValueError("Unknown domain")

    def describe(self):
        if self.name == "Z_n":
            return f"Z_{self.modulus}"
        return self.name

    def parse_scalar(self, text):

        if self.name == "Q":
            return Fraction(text)

        if self.name == "R":
            return float(Fraction(text))

        if self.name in ["Z", "N", "Z_n"]:
            val = Fraction(text)
            if val.denominator != 1:
                raise DomainError("Not valid integer")
            val = val.numerator
            return self.normalize(val)

        raise ValueError()

    def normalize(self, value):

        if self.name == "Q":
            return Fraction(value)

        if self.name == "R":
            return float(value)

        if self.name == "Z":
            if isinstance(value, Fraction):
                if value.denominator != 1:
                    raise DomainError("Non integer result")
                value = value.numerator
            return int(value)

        if self.name == "N":
            if isinstance(value, Fraction):
                if value.denominator != 1:
                    raise DomainError("Non integer result")
                value = value.numerator

            value = int(value)

            if value < 0:
                raise DomainError("Negative not allowed in N")

            return value

        if self.name == "Z_n":
            return int(value) % self.modulus

    def add(self, a, b):
        return self.normalize(a + b)

    def mul(self, a, b):
        return self.normalize(a * b)

    def fmt(self, x):
        return str(x)


# =========================
# Matrix Manipulator
# =========================

@dataclass
class Snapshot:
    matrix: list
    log: list


@dataclass
class MatrixManipulator:

    domain: Domain
    original: list

    matrix: list = field(init=False)
    log: list = field(default_factory=list)

    undo_stack: list = field(default_factory=list)
    redo_stack: list = field(default_factory=list)

    def __post_init__(self):
        self.matrix = deepcopy(self.original)

    def push(self):
        self.undo_stack.append(
            Snapshot(deepcopy(self.matrix), deepcopy(self.log))
        )
        self.redo_stack.clear()

    def swap(self, i, j):

        self.push()

        i -= 1
        j -= 1

        self.matrix[i], self.matrix[j] = self.matrix[j], self.matrix[i]

        self.log.append(f"R{i+1} <-> R{j+1}")

    def linear_row_scale(self, i, s):
        self.push()

        i -= 1

        row_i = self.matrix[i]

        new_row = [self.domain.mul(s, x) for x in row_i]

        self.matrix[i] = new_row
        self.log.append(f"R{i+1} -> {s}R{i+1}")

    def linear_row_op(self, i, j, s, t):

        self.push()

        i -= 1
        j -= 1

        row_i = self.matrix[i]
        row_j = self.matrix[j]

        new_row = []

        for a, b in zip(row_i, row_j):

            v1 = self.domain.mul(s, a)
            v2 = self.domain.mul(t, b)

            new_row.append(self.domain.add(v1, v2))

        self.matrix[i] = new_row

    def linear_row_add(self, i, j, s, t):
        self.linear_row_op(i, j, s, t)
        s_str = f"{s}R{i}" if s != 1 else f"R{i}"
        t_str = f"{t}R{j}" if t != 1 else f"R{j}"
        self.log.append(f"R{i} -> {s_str} + {t_str}")

    def linear_row_sub(self, i, j, s, t):
        self.linear_row_op(i, j, s, -t)
        s_str = f"{s}R{i}" if s != 1 else f"R{i}"
        t_str = f"{t}R{j}" if t != 1 else f"R{j}"
        self.log.append(f"R{i} -> {s_str} - {t_str}")

    def undo(self):

        if not self.undo_stack:
            print("Nothing to undo")
            return

        self.redo_stack.append(Snapshot(deepcopy(self.matrix), deepcopy(self.log)))

        s = self.undo_stack.pop()

        self.matrix = deepcopy(s.matrix)
        self.log = deepcopy(s.log)

    def redo(self):

        if not self.redo_stack:
            print("Nothing to redo")
            return

        self.undo_stack.append(Snapshot(deepcopy(self.matrix), deepcopy(self.log)))

        s = self.redo_stack.pop()

        self.matrix = deepcopy(s.matrix)
        self.log = deepcopy(s.log)

    def print_matrix(self, m):

        rows = [[self.domain.fmt(x) for x in r] for r in m]

        w = [max(len(rows[r][c]) for r in range(len(rows))) for c in range(len(rows[0]))]

        for r in rows:
            line = "  ".join(r[c].rjust(w[c]) for c in range(len(r)))
            print("[", line, "]")

    def display(self):

        print("\n================================================")

        print("Domain:", self.domain.describe())

        print("\nOriginal matrix")
        self.print_matrix(self.original)

        print("\nCurrent matrix")
        self.print_matrix(self.matrix)

        print("\nOperations")

        if not self.log:
            print("(none)")
        else:
            for i, op in enumerate(self.log, 1):
                print(f"{i}. {op}")

        print("================================================\n")


# =========================
# Matrix input
# =========================
def read_matrix(domain):

    print("Enter rows of the matrix separated by spaces.")
    print("Press ENTER on an empty line to finish.\n")

    if domain.name == "Q":
        print("Domain: Q (rational numbers)")
        print("You may enter fractions like: 3/4  -2/5  7\n")

    elif domain.name == "R":
        print("Domain: R (real numbers)")
        print("You may enter decimals or fractions like: 0.5  -3.2  1/2\n")

    elif domain.name == "Z":
        print("Domain: Z (integers)")
        print("Only integers are allowed.\n")

    elif domain.name == "N":
        print("Domain: N (natural numbers)")
        print("Only non-negative integers are allowed.\n")

    elif domain.name == "Z_n":
        print(f"Domain: Z_{domain.modulus}")
        print("Integers will automatically be normalized modulo", domain.modulus)
        print(f"Example: in Z_{domain.modulus}, {domain.modulus + 2} becomes 2\n")

    rows = []
    width = None

    while True:

        line = input(f"row {len(rows)+1}: ").strip()

        if not line:
            break

        vals = [domain.parse_scalar(x) for x in line.split()]

        if width is None:
            width = len(vals)

        elif len(vals) != width:
            print("All rows must have the same number of columns.")
            continue

        rows.append(vals)

    return rows

# =========================
# Parsing new ADD syntax
# =========================

def parse_add_sub(command, parts, domain):

    if len(parts) < 3:
        raise ValueError(f"Usage: {command} i j [-iScale s] [-jScale t]")

    i = int(parts[1])
    j = int(parts[2])

    s = 1
    t = 1

    k = 3

    while k < len(parts):

        if parts[k] == "-iScale":
            s = domain.parse_scalar(parts[k+1])
            k += 2

        elif parts[k] == "-jScale":
            t = domain.parse_scalar(parts[k+1])
            k += 2

        else:
            raise ValueError("Unknown parameter")

    return i, j, s, t


# =========================
# Main CLI
# =========================

def print_help():
    print("Commands:")
    print("  show                 - Display the current matrix and log")
    print("  swap i j             - Swap rows i and j")
    print("  scale i s           - Scale row i by scalar s")
    print("  add i j [-iScale s] [-jScale t] - Add scaled row j to row i")
    print("  sub i j [-iScale s] [-jScale t] - Subtract scaled row j from row i")
    print("  undo                 - Undo the last operation")
    print("  redo                 - Redo the last undone operation")
    print("  quit                 - Exit the program")

def main():

    domain = Domain.parse(input("Enter domain (R, Q, Z, N, Z_n): "))

    matrix = read_matrix(domain)

    m = MatrixManipulator(domain, matrix)

    m.display()
    print_help()
    

    while True:

        try:

            cmd = input("> ").strip().split()

            if not cmd:
                continue

            op = cmd[0].lower()

            if op == "help":
                print_help()

            if op == "quit":
                break

            if op == "show":
                m.display()

            elif op == "swap":

                i = int(cmd[1])
                j = int(cmd[2])

                m.swap(i, j)
                m.display()
            
            elif op == "scale":

                i = int(cmd[1])
                s = domain.parse_scalar(cmd[2])

                m.linear_row_scale(i, s)
                m.display()

            elif op == "add":

                i, j, s, t = parse_add_sub(op, cmd, domain)

                m.linear_row_add(i, j, s, t)

                m.display()

            elif op == "sub":

                i, j, s, t = parse_add_sub(op, cmd, domain)

                m.linear_row_sub(i, j, s, t)

                m.display()

            elif op == "undo":

                m.undo()
                m.display()

            elif op == "redo":

                m.redo()
                m.display()

        except Exception as e:
            print("Error:", e)


if __name__ == "__main__":
    main()