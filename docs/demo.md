# Recordings and repeatable examples

The [original 58-second recording](demo.webm) covers intake, an exact replay, timeout read-back and an invalid-email correction. It preserves the earlier interface; those behaviors are unchanged. The [review-ordering clip](review-update.webm) shows the current interface and the older-inquiry fix. Both are actual local browser recordings with synthetic data and no narration. On GitHub, choose **View raw** to download and play the WebM file; the repository file page does not provide an inline player.

To repeat the review example, run `python app.py --db data/review-demo.db`, then `python demo.py --scenario review-ordering`. Select `review-old-001`, correct only Service from Not sure yet to Automation, and submit. The result is Filed · contact unchanged: zero CRM attempts for the old event, while Current contact still shows New company and `review-new-001`. The newer-inquiry link opens that event. Reusing the same database retains this result, so choose a new database filename to repeat from the start.

For the original flow, start the default server and run `python demo.py`:

1. Choose New inquiry and Fill sample. Inspect the contact input, service and region. Submit the form; the resulting queue item has an owner, contact ID and local draft.
2. Click Replay original event. Inspect the duplicate response and unchanged attempt count. The Contacts view shows how a new inquiry with the same email updates one contact rather than creating another.
3. Open the seeded Casey Park inquiry. The simulator saved a contact, then reported a timeout. It remains uncertain until Verify CRM result reads it back. After verification, the event is completed with one CRM attempt.
4. Open Taylor Quinn. Correct the invalid email and unclassified service, submit the review, and inspect the retained original input and correction history.

You can also edit `rules.json`, submit a new event, and see the changed owner. Try the rate-limit fault to see a due time; wait, then Process due retries. The always-rate-limited case stops after three attempts. A credential fault does not enter the scheduled retry loop.

Fault selection is available only for the local simulator. Never describe these screens as a real HubSpot test. The n8n export has separate [import and execution checks](../n8n/README.md).

## 中文讲解要点

输入是合成咨询，输出是可追踪事件、负责人、联系人更新和本地草稿。先展示正常处理，再展示相同事件重放没有额外写入；然后演示“写完但超时”必须读回核实，最后修正非法邮箱，展示原始提交与人工修正记录。本地 n8n→Python→LocalCRM 已实际运行，HubSpot 和真实模型仍未实连。新增复核片段展示旧咨询留档后，当前联系人仍保留较新的公司名和事件 ID。
