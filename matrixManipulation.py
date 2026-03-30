#!/usr/bin/env python3

from copy import deepcopy
from dataclasses import dataclass, field
from fractions import Fraction
import sympy as sp
import os
import re


# =========================
# Domain handling
# =========================

class DomainError(Exception):
    pass


class Domain:

    def __init__(self, name, modulus=None, is_parametric=False, parameters=None):
        self.name: str = name
        self.modulus: int | None = modulus
        self.is_parametric: bool = is_parametric
        self.parameters: dict = parameters or {}
        self.locals: dict = dict(self.parameters)

    @staticmethod
    def parse(domain_str, is_parametric=False, parameters=None):
        while True:
            s = domain_str.strip().upper()

            if s in ["R", "Q", "Z", "N"]:
                return Domain(s, is_parametric=is_parametric, parameters=parameters)

            elif s.startswith("Z_"):
                tail = s[2:]
                if not tail.isdigit():
                    raise ValueError("For modular arithmetic use Z_n with numeric n, for example Z_5")
                n = int(tail)
                if n <= 0:
                    raise ValueError("Modulus must be positive")
                return Domain("Z_n", modulus=n, is_parametric=is_parametric, parameters=parameters)
            else:
                print("Unknown domain. Please enter one of: R, Q, Z, N, Z_n")

    def describe(self):
        if self.name == "Z_n":
            return f"Z_{self.modulus}"
        return self.name

    def parse_scalar(self, text):
        text = text.strip()

        if self.is_parametric:
            try:
                expr = sp.sympify(text, locals=self.locals)
            except Exception as e:
                raise DomainError(f"Invalid symbolic expression: {text}") from e
            return self.normalize(expr)

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

        raise ValueError("Unsupported domain")

    def normalize(self, value) -> int | float | Fraction | sp.Expr:
        if self.is_parametric:
            expr = sp.simplify(value)

            if self.name == "Q":
                return sp.together(expr)

            if self.name == "R":
                return sp.simplify(expr)

            if self.name == "Z":
                if expr.is_number and not expr.is_integer:
                    raise DomainError("Non integer result")
                return sp.simplify(expr)

            if self.name == "N":
                if expr.is_number:
                    if not expr.is_integer:
                        raise DomainError("Non integer result")
                    if expr.is_negative:
                        raise DomainError("Negative not allowed in N")
                return sp.simplify(expr)

            if self.name == "Z_n":
                return sp.simplify(sp.Mod(expr, self.modulus))

            raise ValueError("Unsupported domain")

        if self.name == "Q":
            return Fraction(value)

        if self.name == "R":
            return float(value)

        if self.name == "Z":
            if isinstance(value, Fraction):
                if value.denominator != 1:
                    raise DomainError("Non integer result")
                value = value.numerator
            if isinstance(value, float) and not value.is_integer():
                raise DomainError("Non integer result")
            return int(value)

        if self.name == "N":
            if isinstance(value, Fraction):
                if value.denominator != 1:
                    raise DomainError("Non integer result")
                value = value.numerator

            if isinstance(value, float) and not value.is_integer():
                raise DomainError("Non integer result")

            value = int(value)
            if value < 0:
                raise DomainError("Negative not allowed in N")

            return value

        if self.name == "Z_n":
            if self.modulus is None:
                raise ValueError("Modulus must be set for Z_n domain")
            return int(value) % self.modulus

        raise ValueError("Unsupported domain")

    def add(self, a, b):
        return self.normalize(a + b)

    def mul(self, a, b):
        return self.normalize(a * b)

    def neg(self, a):
        return self.normalize(-a)

    def fmt(self, x):
        if self.is_parametric:
            return str(sp.simplify(x))
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

    def _check_row(self, i):
        if not (1 <= i <= len(self.matrix)):
            raise IndexError(f"Row index {i} out of range")

    def swap(self, i, j):
        self._check_row(i)
        self._check_row(j)

        self.push()

        i0 = i - 1
        j0 = j - 1

        self.matrix[i0], self.matrix[j0] = self.matrix[j0], self.matrix[i0]
        self.log.append(f"R{i} <-> R{j}")

    def linear_row_scale(self, i, s):
        self._check_row(i)

        self.push()

        i0 = i - 1
        row_i = self.matrix[i0]
        new_row = [self.domain.mul(s, x) for x in row_i]

        self.matrix[i0] = new_row
        
        s_val = self._fmt_scalar(s)

        if self._is_one(s):
            s_str = ""
        elif s_val == "-1":
            s_str = "-"
        else:
            if self.domain.is_parametric:
                expr = sp.sympify(s)

                # if it contains parameters OR is not a simple integer
                if expr.free_symbols or not expr.is_integer:
                    s_str = f"({s_val})"
                else:
                    s_str = s_val
            else:
                # non-parametric mode
                if "/" in s_val or any(c.isalpha() for c in s_val):
                    s_str = f"({s_val})"
                else:
                    s_str = s_val

        self.log.append(f"R{i} -> {s_str}R{i}")

    def linear_row_op(self, i, j, s, t):
        self._check_row(i)
        self._check_row(j)

        self.push()

        i0 = i - 1
        j0 = j - 1

        row_i = self.matrix[i0]
        row_j = self.matrix[j0]

        new_row = []
        for a, b in zip(row_i, row_j):
            v1 = self.domain.mul(s, a)
            v2 = self.domain.mul(t, b)
            new_row.append(self.domain.add(v1, v2))

        self.matrix[i0] = new_row

    def linear_row_add(self, i, j, s, t):
        self.linear_row_op(i, j, s, t)
        s_val = self._fmt_scalar(s)
        if self._is_one(s):
            s_str = ""
        elif s_val == "-1":
            s_str = "-"
        else:
            if self.domain.is_parametric:
                expr = sp.sympify(s)

                # if it contains parameters OR is not a simple integer
                if expr.free_symbols or not expr.is_integer:
                    s_str = f"({s_val})"
                else:
                    s_str = s_val
            else:
                # non-parametric mode
                if "/" in s_val or any(c.isalpha() for c in s_val):
                    s_str = f"({s_val})"
                else:
                    s_str = s_val
        t_val = self._fmt_scalar(t)

        if self._is_one(t):
            t_str = ""
        elif t_val == "-1":
            t_str = "-"
        else:
            if self.domain.is_parametric:
                expr = sp.sympify(t)

                # if it contains parameters OR is not a simple integer
                if expr.free_symbols or not expr.is_integer:
                    t_str = f"({t_val})"
                else:
                    t_str = t_val
            else:
                # non-parametric mode
                if "/" in t_val or any(c.isalpha() for c in t_val):
                    t_str = f"({t_val})"
                else:
                    t_str = t_val
        self.log.append(f"R{i} -> {s_str}R{i} + {t_str}R{j}")

    def linear_row_sub(self, i, j, s, t):
        self.linear_row_op(i, j, s, self.domain.neg(t))
        s_val = self._fmt_scalar(s)
        if self._is_one(s):
            s_str = ""
        elif s_val == "-1":
            s_str = "-"
        else:
            if self.domain.is_parametric:
                expr = sp.sympify(s)

                # if it contains parameters OR is not a simple integer
                if expr.free_symbols or not expr.is_integer:
                    s_str = f"({s_val})"
                else:
                    s_str = s_val
            else:
                # non-parametric mode
                if "/" in s_val or any(c.isalpha() for c in s_val):
                    s_str = f"({s_val})"
                else:
                    s_str = s_val
        t_val = self._fmt_scalar(t)

        if self._is_one(t):
            t_str = ""
        elif t_val == "-1":
            t_str = "-"
        else:
            if self.domain.is_parametric:
                expr = sp.sympify(t)

                # if it contains parameters OR is not a simple integer
                if expr.free_symbols or not expr.is_integer:
                    t_str = f"({t_val})"
                else:
                    t_str = t_val
            else:
                # non-parametric mode
                if "/" in t_val or any(c.isalpha() for c in t_val):
                    t_str = f"({t_val})"
                else:
                    t_str = t_val
        self.log.append(f"R{i} -> {s_str}R{i} - {t_str}R{j}")
        
    def _is_one(self, x):
        if self.domain.is_parametric:
            return sp.simplify(x - 1) == 0
        return x == 1

    def _fmt_scalar(self, x):
        return self.domain.fmt(x)

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

        if not rows:
            print("[]")
            return

        cols = len(rows[0])
        w = [max(len(rows[r][c]) for r in range(len(rows))) for c in range(cols)]

        for r in rows:
            if cols == 1:
                print(f"[ {r[0].rjust(w[0])} ]")
            else:
                left = "  ".join(r[c].rjust(w[c]) for c in range(cols - 1))
                right = r[cols - 1].rjust(w[cols - 1])
                print(f"[ {left} | {right} ]")
                
    def reset(self):
        self.push()
        self.matrix = deepcopy(self.original)
        self.log.append("Reset to original matrix")
    
    def print_log(self, limit=None):
        if not self.log:
            print("(none)")
        else:
            if limit is None or len(self.log) <= limit:
                for i, op in enumerate(self.log, 1):
                    print(f"{i}. {op}")
            else:
                start = max(0, len(self.log) - limit)
                for i, op in enumerate(self.log[start:], start + 1):
                    print(f"{i}. {op}")

    def display(self):
        print("================================================")
        print("Domain:", self.domain.describe(), end="")

        if self.domain.is_parametric:
            params = " ".join(self.domain.parameters.keys())
            print(", Parameters:", params if params else "(none)")
        else:
            print()

        print("\nOriginal matrix")
        self.print_matrix(self.original)

        print("\nCurrent matrix")
        self.print_matrix(self.matrix)

        print("\nOperations")
        self.print_log(limit=5)

        print("================================================\n")
    
    def display_state(self):
        print("================================================")

        print("\nCurrent matrix")
        self.print_matrix(self.matrix)

        print("\nOperations")
        self.print_log(limit=5)

        print("================================================\n")


# =========================
# Matrix input
# =========================

def read_yes_no(prompt):
    while True:
        ans = input(prompt).strip().lower()
        if ans in {"y", "yes"}:
            return True
        if ans in {"n", "no", ""}:
            return False
        print("Please answer yes or no.")

def read_parameters():
    raw = input('Enter parameters separated by spaces (example: "a b c n m"): ').strip()
    if not raw:
        return {}

    names = raw.split()
    bad = [name for name in names if not name.isidentifier()]
    if bad:
        raise ValueError(f"Invalid parameter names: {', '.join(bad)}")

    return {name: sp.Symbol(name) for name in names}

def read_matrix(domain):
    print("Enter rows of the matrix separated by spaces.")
    print("Press ENTER on an empty line to finish.\n")

    if domain.is_parametric:
        print("Parametric mode is ON.")
        print("You may use parameters and expressions like:")
        print("  a, 2*a-b, (a+b)/3, (n-1)*m, (n-a)**2, etc.")
        if domain.name == "Z_n":
            print(f"All entries will be interpreted modulo {domain.modulus}.")
        print()

    if domain.name == "Q":
        print("Domain: Q (rational numbers)")
        print("You may enter fractions like: 3/4  -2/5  7\n")

    elif domain.name == "R":
        print("Domain: R (real numbers)")
        print("You may enter decimals, fractions, or symbolic expressions.\n")

    elif domain.name == "Z":
        print("Domain: Z (integers)")
        print("Numeric input must be integers.")
        if domain.is_parametric:
            print("Symbolic expressions are kept formally.\n")
        else:
            print()

    elif domain.name == "N":
        print("Domain: N (natural numbers)")
        print("Numeric input must be non-negative integers.")
        if domain.is_parametric:
            print("Symbolic expressions are kept formally.\n")
        else:
            print()

    elif domain.name == "Z_n":
        print(f"Domain: Z_{domain.modulus}")
        print("Values are normalized modulo", domain.modulus)
        print(f"Example: in Z_{domain.modulus}, {domain.modulus + 2} becomes 2\n")

    rows = []
    width = None

    while True:
        line = input(f"row {len(rows)+1}: ").strip()

        if not line:
            break

        try:
            vals = [domain.parse_scalar(x) for x in line.split()]

            # check that only allowed parameters appear
            if domain.is_parametric:
                allowed = set(domain.parameters.values())

                for v in vals:
                    if hasattr(v, "free_symbols"):
                        bad = v.free_symbols - allowed
                        if bad:
                            bad_names = ", ".join(str(s) for s in bad)
                            raise DomainError(f"Unknown parameter(s): {bad_names}")

        except Exception as e:
            print(f"Invalid row: {e}")
            print("Please re-enter the row.")
            continue

        if width is None:
            width = len(vals)
        elif len(vals) != width:
            print("All rows must have the same number of columns.")
            continue

        rows.append(vals)

    if not rows:
        raise ValueError("Matrix cannot be empty")

    return rows


# =========================
# Command parsing
# =========================

def parse_add_sub(command, parts, domain):
    if len(parts) < 3:
        raise ValueError(f"Usage: {command} i j [-iScale s] [-jScale t]")

    i = int(parts[1])
    j = int(parts[2])

    s = domain.parse_scalar("1")
    t = domain.parse_scalar("1")

    k = 3
    while k < len(parts):
        option = parts[k].lower()

        if option == "-iscale":
            if k + 1 >= len(parts):
                raise ValueError("Missing value after -iScale")
            s = domain.parse_scalar(parts[k + 1])
            k += 2

        elif option == "-jscale":
            if k + 1 >= len(parts):
                raise ValueError("Missing value after -jScale")
            t = domain.parse_scalar(parts[k + 1])
            k += 2

        else:
            raise ValueError(f"Unknown parameter: {parts[k]}")

    return i, j, s, t


# =========================
# Main CLI
# =========================

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def print_help():
    print("Commands:")
    print("  show                              - Display the current matrix and log")
    print("  swap i j                          - Swap rows i and j")
    print("  scale i s                         - Scale row i by scalar s")
    print("  add i j [-iScale s] [-jScale t]   - R_i -> sR_i + tR_j")
    print("  sub i j [-iScale s] [-jScale t]   - R_i -> sR_i - tR_j")
    print("  undo                              - Undo the last operation")
    print("  redo                              - Redo the last undone operation")
    print("  log                               - Show the full operation log")
    print("  reset                             - Reset to the original matrix")
    print("  clr                               - Clear the screen")
    print("  help                              - Show this help")
    print("  quit                              - Exit the program")


def main():
    is_parametric = read_yes_no("Is the matrix parametric? yes(y)/no(N) Default is 'No': ")

    parameters = {}
    if is_parametric:
        parameters = read_parameters()

    domain = Domain.parse(
        input("Enter domain (R, Q, Z, N, Z_n): "),
        is_parametric=is_parametric,
        parameters=parameters
    )

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

            elif op == "quit":
                break

            elif op == "show":
                m.display()

            elif op == "swap":
                i = int(cmd[1])
                j = int(cmd[2])
                m.swap(i, j)
                m.display_state()

            elif op == "scale":
                i = int(cmd[1])
                s = domain.parse_scalar(cmd[2])
                m.linear_row_scale(i, s)
                m.display_state()

            elif op == "add":
                i, j, s, t = parse_add_sub(op, cmd, domain)
                m.linear_row_add(i, j, s, t)
                m.display_state()

            elif op == "sub":
                i, j, s, t = parse_add_sub(op, cmd, domain)
                m.linear_row_sub(i, j, s, t)
                m.display_state()

            elif op == "undo":
                m.undo()
                m.display_state()

            elif op == "redo":
                m.redo()
                m.display_state()

            elif op == "log":
                m.print_log()

            elif op == "reset":
                m.reset()
                m.display_state()

            elif op == "clr":
                clear_screen()
                m.display()

            else:
                print("Unknown command. Type 'help' for usage.")

        except Exception as e:
            print("Error:", e)


if __name__ == "__main__":
    main()