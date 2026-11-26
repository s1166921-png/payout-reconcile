"""Offline evidence-first payout reconciliation."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, timedelta
from decimal import Decimal
import json
import re
import sys

def day(value):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:[ T][0-9]{2}:[0-9]{2}(?::[0-9]{2})?(?:Z| ?[A-Z]{2,5}|[+-][0-9]{2}:?[0-9]{2})?)?", value):
        raise ValueError("unsupported date format (use YYYY-MM-DD)")
    return date.fromisoformat(value[:10])

def money(value, mark):
    thousands = "," if mark == "." else "."
    plain, group = re.escape(mark), re.escape(thousands)
    if len(value) > 64 or not re.fullmatch(rf"[-+]?(?:[0-9]+|[0-9]{{1,3}}(?:{group}[0-9]{{3}})+)(?:{plain}[0-9]+)?", value):
        raise ValueError("invalid amount for selected decimal convention")
    return Decimal(value.replace(thousands, "").replace(mark, "."))

def rows(stream, columns, *, delimiter=",", mark=".", native=False, credit=False):
    reader = csv.DictReader(stream, delimiter=delimiter, strict=True)
    headers = reader.fieldnames or []
    if len(set(headers)) != len(headers) or not set(columns[:4 if not credit else 3]).issubset(headers):
        raise ValueError("missing or duplicate input columns: expected " + ", ".join(columns[:4 if not credit else 3]))
    for r in reader:
        try:
            if None in r or None in r.values():
                raise ValueError("wrong number of columns")
            raw = [r.get(k, "").strip() for k in columns]
            if credit:
                d, c, amount, ref = raw
            else:
                ref, d, c, amount = raw
                if native and not any((d, c, amount)):
                    continue
                if not ref:
                    raise ValueError("missing settlement ID")
            if not re.fullmatch("[A-Z]{3}", c):
                raise ValueError("currency must be a three-letter uppercase code")
            d, amount = day(d), money(amount, mark)
            if credit and amount <= 0:
                continue
            yield ref, d, c, amount, reader.line_num
        except ValueError as ex:
            raise ValueError(f"line {reader.line_num}: {ex}") from ex

def check(settlements, receipts, *, native=False, decimal_mark=".", bank_decimal=".",
          coverage=None, indirect=False, bank_columns=("date","currency","amount","settlement_id"),
          window=5):
    sk = ("settlement-id","deposit-date","currency","total-amount") if native else ("id","date","currency","amount")
    settlements = list(rows(settlements, sk, delimiter="\t" if native else ",", mark=decimal_mark, native=native))
    receipts = list(rows(receipts, bank_columns, mark=bank_decimal, credit=True))
    by_ref, unreferenced = defaultdict(list), defaultdict(list)
    known = Counter(s[0] for s in settlements)
    for r in receipts:
        if coverage and not coverage[0] <= r[1] <= coverage[1]:
            raise ValueError("receipt date falls outside the declared statement coverage")
        if r[0]:
            by_ref[r[0]].append(r)
        else:
            unreferenced[(r[2], r[3])].append(r)
    span = timedelta(days=window)
    options, seen = {}, Counter()
    for ref, d, c, amt, line in settlements:
        if not indirect and known[ref] == 1 and amt > 0 and ref not in by_ref:
            opts = options[line] = [r for r in unreferenced[(c, amt)] if d <= r[1] <= d + span]
            seen.update(r[4] for r in opts)
    results = []
    for ref, d, c, amt, line in settlements:
        hits, opts = by_ref.get(ref, []), options.get(line, [])
        evidence = []
        if known[ref] > 1:
            status = "duplicate_settlements"
        elif amt <= 0:
            status = "not_positive_payout"
        elif indirect:
            status = "missing_provider_evidence"
        elif len(hits) > 1:
            status, evidence = "duplicate_receipts", hits
        elif hits:
            r = hits[0]
            evidence = hits
            status = ("currency_mismatch" if r[2] != c else "amount_mismatch" if r[3] != amt
                      else "review_timing" if not d <= r[1] <= d + span else "matched")
        elif opts:
            status = "review_candidate" if len(opts) == 1 and seen[opts[0][4]] == 1 else "ambiguous_candidate"
            evidence = opts
        elif not coverage or not (coverage[0] <= d and d + span <= coverage[1]):
            status = "coverage_unverified"
        else:
            status = "not_found_in_statement"
        results.append(dict(id=ref, date=d.isoformat(), currency=c, amount=str(amt), source_line=line,
                            status=status, receipts=[dict(line=r[4],date=r[1].isoformat(),currency=r[2],
                                                         amount=str(r[3])) for r in evidence]))
    return results

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("settlements")
    p.add_argument("receipts")
    p.add_argument("--amazon-v2", action="store_true")
    p.add_argument("--indirect", action="store_true", help="input is final bank statement, not the first receiving provider's statement")
    p.add_argument("--coverage", nargs=2, metavar=("START", "END"))
    p.add_argument("--window", type=int, default=5, help="review window in calendar days; not a payment SLA")
    p.add_argument("--settlement-decimal", choices=[".", ","], default=".")
    p.add_argument("--bank-decimal", choices=[".", ","], default=".")
    p.add_argument("--bank-columns", nargs=4, metavar="COLUMN", default=("date","currency","amount","settlement_id"),
                   help="date, currency, amount, trusted settlement ID column (the last column may be absent)")
    a = p.parse_args()
    try:
        coverage = tuple(map(day, a.coverage)) if a.coverage else None
        if coverage and coverage[0] > coverage[1]:
            raise ValueError("coverage start must not be after end")
        if not 0 <= a.window <= 90 or len(set(a.bank_columns)) != 4:
            raise ValueError("window must be 0–90 days and bank columns must be distinct")
        with open(a.settlements, encoding="utf-8-sig", newline="") as s, open(a.receipts, encoding="utf-8-sig", newline="") as b:
            results = check(s, b, native=a.amazon_v2, coverage=coverage, window=a.window, indirect=a.indirect,
                            decimal_mark=a.settlement_decimal, bank_decimal=a.bank_decimal,
                            bank_columns=a.bank_columns)
        if not results:
            raise ValueError("no settlement summary rows")
    except (ValueError, OSError, csv.Error, OverflowError) as ex:
        print(f"Input error: {ex}", file=sys.stderr)
        return 2
    print(json.dumps({"version":1, "settlements":results}, indent=2))
    return int(any(r["status"] not in {"matched", "not_positive_payout"} for r in results))

if __name__ == "__main__":
    sys.exit(main())
