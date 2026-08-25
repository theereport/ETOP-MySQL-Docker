SELECT 
TARODTEADD AS 'Creation Date',
TARONUMCST AS 'Customer Number',
TARONUMINV as 'Invoice Number',
TARONUMCNT AS 'Count Number',
TARONUMREF AS 'Reference Number',
TAROAMTOPN AS 'Open Amount',
TAROAMTORG AS 'Original Amount',
TAROTYPTRN AS 'Transaction Type',
TARODBCR AS 'Debit or Credit'
FROM DTA273.TMAROP
WHERE TARONUMREF LIKE '%ZT%'
  AND TAROAMTOPN <> 0;