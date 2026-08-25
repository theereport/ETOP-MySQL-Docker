# Install ETOP 0.6.9 Editable Lockbox Allocation and Credit Sign Control

This release is built on
`ETOP-Integrated-Agent-1-4-Current-20260730-0.6.8.zip`. It preserves the
Complete Blueprint, Agent Operating Contract, high-throughput 125-of-125
preparation, resumable checkpoints, and exact due-date allocation while making
the prepared allocation directly editable and correcting ERP credit signs.

1. Stop the ETOP frontend and backend.
2. Extract this ZIP to a temporary folder outside
   `C:\Users\Josh.Corbit\vite-project`.
3. Open PowerShell in the extracted folder.
4. Run:

```powershell
powershell.exe -ExecutionPolicy Bypass -File ".\Install-ETOP-Integrated-Release.ps1"
```

The installer expects the project at:

```text
C:\Users\Josh.Corbit\vite-project
```

For another location:

```powershell
powershell.exe -ExecutionPolicy Bypass `
  -File ".\Install-ETOP-Integrated-Release.ps1" `
  -ProjectRoot "C:\Path\To\vite-project"
```

The installer validates the current integrated ETOP baseline and creates a
timestamped backup under `.etop-backups` before copying any files. If the
baseline has changed, it stops without modifying the project so the differences
can be reviewed.

After installation:

1. restart the backend and frontend;
2. search `high risk customers`, `lockbox`, and `SOP`;
3. open the highest-priority customer from the dashboard;
4. select the existing 125-transaction PNC lockbox;
5. resume and confirm it continues with the first missing transaction without
   rerunning OCR, using the controlled faster preparation path;
6. confirm preparation reaches 125 of 125;
7. confirm the exception count, review table, and reviewed export remain
   unavailable until preparation reaches 125 of 125;
8. close and reopen Lockbox Automation, then confirm the completed preparation
   opens without recalculation;
9. confirm the matched customer number, name, phone, street, city, state, and
   ZIP are already populated from ERP;
10. test the $1,129.36 example and confirm all six July 10 invoices appear,
   later August invoices do not, and Due Date is visible in allocation detail;
11. open the recommendation for customer 431664 and confirm invoice 431063896
    displays as a Credit with an open/apply amount of `-$916.00`, while the raw
    ERP evidence states `Debit · negative source amount`;
12. change an apply amount, remove an incorrect invoice, add an ERP open
    invoice, and add a blank row directly inside Editable Invoice Allocation;
13. confirm a positive apply amount on an ERP credit is blocked from save;
14. manually select customer 520459 and confirm the same six-invoice
    recommendation loads automatically without a separate Refresh click;
15. confirm an invoice with multiple possible ERP owners remains in review
    instead of being selected automatically;
16. confirm a preparation error remains in review while later transactions
    continue processing;
17. confirm prepared/balanced transactions are not marked Approved;
18. confirm no ERP posting occurs; and
19. confirm SQL Studio still uses the local `SqlEditor.tsx`.
