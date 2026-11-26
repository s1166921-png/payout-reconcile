# Payout Reconcile · 跨境回款对账

**平台说已结算，这笔款在收款流水里找得到吗？** 对照 Amazon 结算表和收款流水，列出需要人工复核的差异。离线运行，不需要 API 密钥，也不上传报表。

| 虚构样例 | 结果 |
| --- | --- |
| A · EUR 95.00 | 可信结算编号、币种、金额及日期窗口一致 |
| B · EUR 123.45 | 金额及日期相符，但没有可信编号，须复核 |
| C · EUR 55.10 | 在声明覆盖的流水中没找到，不代表资金丢失 |

## 30 秒试用 / Quick start

需要 Python 3.10+，无第三方依赖。Windows 可将 `python` 换为 `py`。

```sh
git clone https://github.com/s1166921-png/payout-reconcile.git
cd payout-reconcile
python payout.py examples/amazon.tsv examples/receipts.csv --amazon-v2 --settlement-decimal "," --coverage 2026-11-01 2026-11-30
```

样例故意含差异。退出码 `0` 无待复核项；`1` 有待复核项（仍输出 JSON）；`2` 输入错误。结果包含原始行号。

- 平台输入：Amazon [Flat File V2 TSV](https://developer-docs.amazon/sp-api/docs/report-type-values-settlement) 读取结算汇总行，不合计交易明细。通用 CSV 用 `id,date,currency,amount`，不加 `--amazon-v2`。
- 收款 CSV：`date,currency,amount,settlement_id`。最后一列可缺省；仅在你已确认对应关系时填入平台结算编号。银行 Trace ID 不是 Amazon settlement ID。用 `--bank-columns 日期 币种 金额 结算编号` 映射其他列名。CSV 使用 UTF-8，日期使用 ISO 格式。
- 设置 `--coverage 起日 止日` 为实际流水覆盖区间；`--window` 控制候选窗口，默认 5 个日历日，仅用于筛查，不是到账承诺。只按同币种匹配，金额使用十进制计算。
- 若 Amazon 先付到收款服务商，再提现到银行，应优先核对服务商流水。若手里只有最终银行流水，使用 `--indirect`，工具不会声称验证了第一段回款。不猜汇率，不验证拆分/合并付款，不写账。

## English

Offline reconciliation for Amazon Flat File V2 TSV or generic payout CSV against the receiving account's CSV. An exact trusted ID, currency, amount and review window can establish a match in the supplied statement. An amount/date-only match is a candidate, not confirmation. If a payment provider receives the payout first, a final bank statement alone cannot verify the first leg; use `--indirect`. See the synthetic demo above. Run tests with `python -m unittest -v`.

Please report issues with fictional data, not customer or bank records. MIT.

Related: [zh-claim-lint](https://github.com/s1166921-png/zh-claim-lint) checks dates and amounts in Chinese drafts against their sources.
