import io
import json
import subprocess
import sys
import unittest

import payout

class Reconciliation(unittest.TestCase):
    def assess(self, bank, **kwargs):
        s = 'settlement-id\tdeposit-date\ttotal-amount\tcurrency\tamount\nS1\t2026-11-10\t95,00\tEUR\t\nS1\t\t\t\t25,00\n'
        b = 'date,currency,amount,settlement_id\n' + bank
        return payout.check(io.StringIO(s), io.StringIO(b), native=True,
                            decimal_mark=',', **kwargs)[0]['status']

    def test_trusted_id_and_eu_amount(self):
        self.assertEqual(self.assess('2026-11-11,EUR,95.00,S1\n'), 'matched')

    def test_date_amount_only_candidate(self):
        self.assertEqual(self.assess('2026-11-11,EUR,95.00,\n'), 'review_candidate')

    def test_duplicate(self):
        self.assertEqual(self.assess('2026-11-11,EUR,95.00,S1\n'*2), 'duplicate_receipts')

    def test_wrong_currency(self):
        self.assertEqual(self.assess('2026-11-11,USD,95.00,S1\n'), 'currency_mismatch')

    def test_amount_mismatch(self):
        self.assertEqual(self.assess('2026-11-11,EUR,94.99,S1\n'), 'amount_mismatch')

    def test_two_leg_requires_provider_evidence(self):
        self.assertEqual(self.assess('2026-11-11,EUR,95.00,S1\n', indirect=True), 'missing_provider_evidence')

    def test_unknown_coverage(self):
        self.assertEqual(self.assess(''), 'coverage_unverified')

    def test_covered_no_record(self):
        self.assertEqual(self.assess('', coverage=(payout.day('2026-11-01'),payout.day('2026-11-20'))), 'not_found_in_statement')

    def test_shared_candidate(self):
        s = 'id,date,currency,amount\nS1,2026-11-10,EUR,95\nS2,2026-11-10,EUR,95\n'
        b = 'date,currency,amount,settlement_id\n2026-11-11,EUR,95,\n'
        self.assertEqual([r['status'] for r in payout.check(io.StringIO(s),io.StringIO(b))], ['ambiguous_candidate']*2)

    def test_cli_demo(self):
        p = subprocess.run([sys.executable,'payout.py','examples/amazon.tsv','examples/receipts.csv',
                            '--amazon-v2','--settlement-decimal',',','--coverage','2026-11-01','2026-11-30'],
                           capture_output=True,text=True)
        self.assertEqual(p.returncode, 1, p.stderr)
        self.assertEqual([r['status'] for r in json.loads(p.stdout)['settlements']],
                         ['matched','review_candidate','not_found_in_statement'])
