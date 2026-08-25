SELECT
    l.TIHLNUMSTR AS "STORE #",
    h.TIHHSTECST AS "STATE",
    h.TIHHTAXAUT AS "TAX AUTHORITY",
    SUM(h.TIHHTOTINV) AS "TOTAL INVOICE TOTAL",
    SUM(
        CASE
            WHEN l.TIHLPRD = '99SLTAX' THEN -l.TIHLPRC
            ELSE l.TIHLPRC
        END
    ) AS "TOTAL SALES TAX PRICE",
    concat(h.tihhstecst,h.tihhtaxaut) as "Tax Lookup",
    concat("2500-",l.tihlnumstr,"-0") as "GL Posting",
    if(h.tihhstecst = 6,'Quarterly','Monthly') as "Filing Frequency"
FROM DTA273.TMIHSL l
JOIN DTA273.TMIHSH h
    ON h.TIHHNUMCST = l.TIHLNUMCST
   AND h.TIHHNUMINV = l.TIHLNUMINV
WHERE l.TIHLPRD IN ('SLTAX', '99SLTAX')
  AND l.TIHLPRC <> 0
  AND h.TIHHYRPRIN = 202605
  AND h.TIHHVOIDYN = 'N'
GROUP BY
    l.TIHLNUMSTR,
    h.TIHHSTECST,
    h.TIHHTAXAUT
ORDER BY
    l.TIHLNUMSTR,
    h.TIHHSTECST,
    h.TIHHTAXAUT;