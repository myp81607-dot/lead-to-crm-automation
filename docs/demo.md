# A short demo you can repeat

This is a synthetic personal demonstration. The [browser recording](demo.webm) shows the actual local backend and UI; it has no narration. Screenshots are captured from the same application, not designed mockups.

1. **0–20 seconds:** Start `python app.py`, run `python demo.py`, then choose New inquiry and Fill sample. Point out the contact input, service and region. Submit the form; the resulting queue item has an owner, contact ID and local draft.
2. **20–35 seconds:** Click Replay original event. Show the duplicate response and unchanged attempt count. Use the Contacts view to explain that a new inquiry with the same email updates one contact rather than creating another.
3. **35–55 seconds:** Open the seeded Casey Park inquiry. The simulator saved a contact, then reported a timeout. It remains uncertain until Verify CRM result reads it back. Click verification and show the completed state with one CRM attempt.
4. **55–90 seconds:** Open Taylor Quinn. The invalid email and unclassified service are visible. Correct the email and service, submit the review, and inspect the retained original input and correction history.

You can also edit `rules.json`, submit a new event, and see the changed owner. Try the rate-limit fault to see a due time; wait, then Process due retries. The always-rate-limited case stops after three attempts. A credential fault does not enter the scheduled retry loop.

Fault selection is available only for the local simulator. Never describe these screens as a real HubSpot test. The n8n export has separate [import and execution checks](../n8n/README.md).

## 中文讲解要点

输入是合成咨询，输出是可追踪事件、负责人、联系人更新和本地草稿。先展示正常处理，再展示相同事件重放没有额外写入；然后演示“写完但超时”必须读回核实，最后修正非法邮箱，展示原始提交与人工修正记录。强调本地功能已运行，而 HubSpot、真实模型和 n8n 运行仍未实连验证。
