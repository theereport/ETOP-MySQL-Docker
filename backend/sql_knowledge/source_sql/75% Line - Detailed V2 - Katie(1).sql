SELECT
    CUNUMBER AS 'Customer Number',
    CUNAME AS 'Customer Name',

    CONCAT('$', FORMAT(CUCRLIMIT, 2)) AS 'Credit Limit',

    CONCAT('$', FORMAT(CUBALANCE, 2)) AS 'Current Balance',

    CONCAT(
        '$',
        FORMAT((CUBALANCE - CUCRLIMIT), 2)
    ) AS '$ Amount Over',

    CASE
        WHEN (
            CURVCPM30
            + CURVCPM60
            + CURVCPM90
            + CURVCPM120
        ) > 0
        THEN 'Yes'
        ELSE 'No'
    END AS 'Past Due?',

    CASE CUTERMS
        WHEN 0 THEN 'C.O.D.'
        WHEN 1 THEN 'DUE ON THE 10TH'
        WHEN 2 THEN '30/60 NET 10TH'
        WHEN 3 THEN '30/60/90 NET 10TH'
        WHEN 4 THEN '60 NET 10TH'
        WHEN 6 THEN 'TENANTS DUE ON THE 6TH'
        WHEN 7 THEN 'COD - ONLY'
        WHEN 8 THEN 'C.O.D. - CASH'
        WHEN 9 THEN '90 NET 10TH'
        WHEN 11 THEN '90/120/150 NET 10TH'
        WHEN 12 THEN '10TH NO ROLLING'
        WHEN 13 THEN '6 PAYMENTS'
        WHEN 15 THEN '60/90'
        WHEN 16 THEN '90/120'
        WHEN 17 THEN '30/60/90/120'
        WHEN 18 THEN '60 DAYS NO ROLLING'
        WHEN 19 THEN '120 NET 10TH'
        WHEN 20 THEN '30 NET 10TH ROLL ON 26TH'
        WHEN 22 THEN '12 MONTHLY PAYMENTS'
        WHEN 30 THEN 'PAID BY CREDIT CARD'
        WHEN 31 THEN 'DUE NEXT WEEK'
        WHEN 32 THEN 'DUE IN 150 DAYS, NET 10TH'
        WHEN 35 THEN 'ONE DAY TERMS'
        WHEN 40 THEN '2% 30, NET 60'
        WHEN 777 THEN 'INTERCOMPANY'
        ELSE CONCAT('UNKNOWN (', CUTERMS, ')')
    END AS 'Payment Terms',

    CONCAT(
        '$',
        FORMAT(
            ROUND(
                (
                    CUYTDSALES
                    / NULLIF(DAYOFYEAR(CURDATE()), 0)
                    * 365
                ) / 1000,
                0
            ) * 1000,
            0
        )
    ) AS 'Annualized Sales Projection',

    CONCAT(
        '$',
        FORMAT(
            ROUND(
                (
                    (
                        CUYTDSALES
                        / NULLIF(DAYOFYEAR(CURDATE()), 0)
                        * 365
                    ) / 12 * 2
                ) / 500,
                0
            ) * 500,
            0
        )
    ) AS 'Credit Line Expected',

    CONCAT(
        '$',
        FORMAT(
            ROUND(
                (
                    (
                        ROUND(
                            (
                                (
                                    CUYTDSALES
                                    / NULLIF(DAYOFYEAR(CURDATE()), 0)
                                    * 365
                                ) / 12 * 2
                            ) / 500,
                            0
                        ) * 500
                    ) - CUCRLIMIT
                ) / 500,
                0
            ) * 500,
            0
        )
    ) AS 'Increase(Decrease) Potential'

FROM DTA273.TMCUST

WHERE CUBALANCE >= (CUCRLIMIT * 0.75)
  AND CUEXFLAG4 <> 'X'
  AND CUCRLIMIT <> 100.00
  AND CUCRLIMIT <> 0.00

ORDER BY
    /* Past-due customers first */
    CASE
        WHEN (
            CURVCPM30
            + CURVCPM60
            + CURVCPM90
            + CURVCPM120
        ) > 0
        THEN 0
        ELSE 1
    END,

    /* Within both past-due and non-past-due groups:
       terms 0 first, then 7, then 8, then all others */
    CASE
        WHEN CUTERMS = 0 THEN 0
        WHEN CUTERMS = 7 THEN 1
        WHEN CUTERMS = 8 THEN 2
        ELSE 3
    END,

    /* Remaining terms codes in numerical order */
    CUTERMS ASC,

    /* Highest credit utilization first within each terms code */
    (CUBALANCE / NULLIF(CUCRLIMIT, 0)) DESC;