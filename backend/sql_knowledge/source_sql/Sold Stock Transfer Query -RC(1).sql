SELECT
    T02.CUROUTECD AS 'Route Code',

    CASE
        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '1A','1B','1C','1D','1E','1F','1G','1H','1J','1K',
            '1L','1M','1N','1P','1R','1T','1V','1W','1X','1Y',
            '01','S1'
        ) THEN '1'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '2A','2B','2C','2E','2G','2H','02','S2'
        ) THEN '2'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '3A','3B','3C','3D','3E','3F','3G','3H','3I','3J',
            '3K','3L','3M','3N','03','S3'
        ) THEN '3'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'ZA','ZB','ZC','ZD','ZE','ZF','ZG','ZH','ZI','ZJ',
            'ZK','ZL','ZM','ZN','ZS','ZT','ZU','ZV','ZW','ZX',
            'ZY','ZZ','Z1','Z2','Z3','Z4','Z5','Z6','04','S4'
        ) THEN '4'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '05','S5'
        ) THEN '5'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '6A','6B','6C','6D','6E','6F','6G','6H','6I','6J',
            '06','S6'
        ) THEN '6'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '7A','7B','7C','7D','7F','7G','7H','7I','7J','7K',
            '07','S7'
        ) THEN '7'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'KO','KP','KS','KT','KV','KW','08','TK'
        ) THEN '8'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'S9'
        ) THEN '9'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'HT','HU','HV','HW','14','TH'
        ) THEN '14'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'UA','UB','UC','UD','UE','UF','UG','UH','UI','UJ',
            'UK','UM','UN','15','SU'
        ) THEN '15'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'LL','LM','LN','LP','LQ','LR','LS','LT','LU','LW',
            '17','TL'
        ) THEN '17'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'FL','FM','FN','FP','FQ','FR','FS','FT','FV','FW',
            'FX','18','S0'
        ) THEN '18'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'F5','F6','F7','F8','20','TB'
        ) THEN '20'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'RL','RM','RN','RO','RR','RS','RT','RU','RV','RW',
            '21','TR'
        ) THEN '21'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'YA','YB','YC','YD','YE','YF','YG','YH','YK','YL',
            '22','SY','78'
        ) THEN '22'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'QA','QB','QC','QD','QE','QF','QG','QH','QI','QJ',
            'QK','QL','QM','QN','24','SQ'
        ) THEN '24'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'K6','K7','K8','K9','25','TC'
        ) THEN '25'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'DU','DV','DW','DX','DY','27','SJ'
        ) THEN '27'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '8O','8P','8Q','8R','8S','8T','8U','8V','8W',
            '31','SP'
        ) THEN '31'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'MA','MB','MC','MD','ME','MF','MG','MH','MI','MJ',
            'MK','33','SM'
        ) THEN '33'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'B1','B2','B3','B5','B6','B7','B8','B9','34','TE'
        ) THEN '34'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'P1','P2','P3','P4','P5','P6','P7','P8','35','TG'
        ) THEN '35'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'G1','G3','G4','G5','G6','G7','G8','G9','GT','GU',
            'GV','37','TT'
        ) THEN '37'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'OA','OB','OC','OD','OE','OF','OG','OH','OI',
            '41','TO'
        ) THEN '41'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'CB','CD','CH','CI','CK','CL','CM','CN','CO','CP',
            'CQ','CS','CT','CU','CV','CW','CX','CY','42','SC',
            '94'
        ) THEN '42'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'IA','IB','IC','ID','IE','IF','IG','IH','II','IJ',
            'IK','IM','IP','IQ','IS','43','SI','96'
        ) THEN '43'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'XA','XB','XD','XE','XF','XG','XH','XI','XJ','XK',
            'XL','XM','XN','XP','XQ','47','SX','97'
        ) THEN '47'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '48','95'
        ) THEN '48'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'RA','RB','RC','RD','RE','RF','RG','49','SR'
        ) THEN '49'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '50'
        ) THEN '50'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'EA','EB','EC','ED','EE','EF','EG','EH','EI','EJ',
            'EK','EL','EM','EN','EP','EQ','ER','ES','ET',
            '51','SE','91'
        ) THEN '51'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'FA','FB','FC','FD','FE','FF','FG','FH','52','SF'
        ) THEN '52'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'BA','BB','BC','BD','BE','BF','BG','BJ',
            '53','SB','79'
        ) THEN '53'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'YQ','YR','YT','YU','YV','YW','YX','YY','Y1','Y2',
            'Y3','Y4','55','SN'
        ) THEN '55'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'WA','WB','WC','WD','WE','WF','WG','WH','WI','WJ',
            'WK','WL','WM','57','SW'
        ) THEN '57'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'KA','KB','KC','KD','KE','KF','KG','KH','KJ','KK',
            'KL','59','SK'
        ) THEN '59'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'L6','L7','L8','L9','60','TN'
        ) THEN '60'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'QS','QT','QU','QV','QW','QX','QY','61','SG'
        ) THEN '61'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '6Q','6R','6S','6U','6V','6W','6X','6Y',
            '64','SZ'
        ) THEN '64'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '7N','7P','7R','7S','7T','65','TD'
        ) THEN '65'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'GA','GB','GC','GD','GE','GF','GG','GI','GJ','GK',
            'GL','70','TM'
        ) THEN '70'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'A2','A3','A4','A5','A7','A8','71','TF'
        ) THEN '71'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'WN','WP','WQ','WR','WS','WT','WU','WV','WW','WX',
            'WY','WZ','72','TS'
        ) THEN '72'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'LA','LB','LC','LD','LE','LF','LG','LH','LI','LJ',
            '73','TI'
        ) THEN '73'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'JN','JP','JQ','JR','JS','JT','JU','JV','JW','JX',
            'JY','JZ','J1','J2','J3','74','TP'
        ) THEN '74'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'N1','N2','N3','N4','N6','N7','75','TW'
        ) THEN '75'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'H1','H2','H3','H5','H6','H7','H8','76','TU'
        ) THEN '76'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'VN','VP','VQ','VR','VS','VU','VV','VW','VX','VY',
            'VZ','V1','V2','77','TV'
        ) THEN '77'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'AA','AB','AC','AD','AE','AF','AG','AH','AI','AJ',
            'AK','80','SA'
        ) THEN '80'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '2Q','2R','2S','2T','2U','2V','2W','2X','82','SL'
        ) THEN '82'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'M1','M2','M3','M5','M6','M7','M8','83','SV','89'
        ) THEN '83'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'DA','DB','DC','DD','DE','DG','DH','DI','DJ','DK',
            'DL','DM','DN','DP','DQ','84','92'
        ) THEN '84'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            'HA','HB','HC','HD','HF','HG','HH','HI','HJ','HK',
            'HL','HM','HP','86','SH'
        ) THEN '86'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '8A','8B','8D','8E','8F','8G','8H','8I','8J','8K',
            '88','S8','ST'
        ) THEN '88'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN (
            '5D','5F','5G','5H','5J','5K','5M','5P','5R','5T',
            '5W'
        ) THEN 'LTL'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = 'TZ'
            THEN 'ZT'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '19'
            THEN 'UPS'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = 'TQ'
            THEN 'N/A'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '90'
            THEN 'Amazon - 1'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '91'
            THEN 'Amazon - 51'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '92'
            THEN 'Amazon - 84'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '93'
            THEN 'Amazon - 24'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '94'
            THEN 'Amazon - 42'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '95'
            THEN 'Amazon - 48'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '96'
            THEN 'Amazon - 43'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '97'
            THEN 'Amazon - 47'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '98'
            THEN 'Delticom / Simple'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '9A'
            THEN 'Walmart- Loc 1'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '9B'
            THEN 'Walmart- Loc 51'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '9C'
            THEN 'Walmart- Loc 42'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '9D'
            THEN 'Walmart- Loc 84'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '9E'
            THEN 'Walmart- Loc 4'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '9F'
            THEN 'Walmart- Loc 8'

        WHEN UPPER(TRIM(T02.CUROUTECD)) IN ('1O','1I')
            THEN 'Delphos Special'

        WHEN UPPER(TRIM(T02.CUROUTECD)) = '10'
            THEN 'Special Marketing- Dave'

        ELSE 'NOT MAPPED'
    END AS 'Store Number',

    T01.TIHLDTEINP AS 'Input Date',
    T02.CUNAME AS 'CUSTOMER NAME',
    T01.TIHLNUMCST AS 'CUSTOMER #',
    T04.PDVENDOR AS 'PRODUCT VENDOR',

    CASE
        WHEN UPPER(V.PVNAMVEN) LIKE '%POSTAL%' THEN 'HANKOOK'
        WHEN UPPER(V.PVNAMVEN) = 'ALBIN BUSINESS COPIERS' THEN 'BRIDGESTONE'
        WHEN UPPER(V.PVNAMVEN) = 'BRIDGESTONE/FIRESTONE' THEN 'FIRESTONE'
        WHEN UPPER(V.PVNAMVEN) = 'ALLEN COUNTY TREASURER' THEN 'FUZION'
        WHEN UPPER(V.PVNAMVEN) = 'H.E. POWER SUPPLY' THEN 'REGENCY'
        WHEN UPPER(V.PVNAMVEN) = 'FIRESTONE TUBE COMPANY' THEN 'FIRESTONE TUBES'
        WHEN UPPER(V.PVNAMVEN) = 'AMERICAN RACING CUSTOM WH' THEN 'LAUFENN'
        WHEN UPPER(V.PVNAMVEN) = 'MICKEY THOMPSON TIRES' THEN 'MICKEY THOMPSON'
        WHEN UPPER(V.PVNAMVEN) = 'MICHELIN NORTH AMERICA' THEN 'MICHELIN'
        WHEN UPPER(V.PVNAMVEN) = 'SUPER TIRE / METRO 25' THEN '#N/A'
        WHEN UPPER(V.PVNAMVEN) = 'MICHELIN MOVE TO 120' THEN 'BFGOODRICH'
        WHEN UPPER(V.PVNAMVEN) = 'G NEIL DIRECT MAIL' THEN 'COOPER'
        WHEN UPPER(V.PVNAMVEN) = 'DAN LUCKE' THEN 'STARFIRE'
        WHEN UPPER(V.PVNAMVEN) = 'COOPER - GOODYEAR' THEN 'MASTERCRAFT'
        WHEN UPPER(V.PVNAMVEN) = 'SACRED HEART HOME' THEN 'ROADMASTER'
        WHEN UPPER(V.PVNAMVEN) = 'TIM GRICE' THEN 'PIRELLI'
        WHEN UPPER(V.PVNAMVEN) = 'YOKOHAMA TWS NORTH' THEN 'TRELLEBORG'
        WHEN UPPER(V.PVNAMVEN) = 'THE CARLSTAR GROUP LLC' THEN 'CARLSTAR-CARLISLE'
        WHEN UPPER(V.PVNAMVEN) = 'CONTINENTAL TIRE NORTH' THEN 'GENERAL'
        WHEN UPPER(V.PVNAMVEN) = 'AUTOZONE INC.' THEN 'CONTINENTAL'
        WHEN UPPER(V.PVNAMVEN) = 'CO-OP FARM' THEN 'GOODYEAR FARM'
        WHEN UPPER(V.PVNAMVEN) = 'TITAN MARKETING SERVICES' THEN 'TITAN FARM'
        WHEN UPPER(V.PVNAMVEN) = 'GOODYEAR TIRE & RUBBER CO' THEN 'GOODYEAR'
        WHEN UPPER(V.PVNAMVEN) = 'AT&T' THEN 'DUNLOP'
        WHEN UPPER(V.PVNAMVEN) = 'KALIDA TRUCK EQUIPMENT' THEN 'KELLY'
        WHEN UPPER(V.PVNAMVEN) = 'SUTONG CHINA TIRE' THEN 'SUPER CARGO'
        WHEN UPPER(V.PVNAMVEN) = 'YOKOHAMA TIRE CORP.' THEN 'YOKOHAMA'
        WHEN UPPER(V.PVNAMVEN) = 'KUMHO TIRE U.S.A. INC' THEN 'KUMHO'
        WHEN UPPER(V.PVNAMVEN) = 'DUNLOP TIRES NORTH' THEN 'FALKEN'
        WHEN UPPER(V.PVNAMVEN) = 'BKT TIRES-WIRE' THEN 'BKT TIRES'
        WHEN UPPER(V.PVNAMVEN) = 'ALLEN RUBBER COMPANY INC.' THEN 'GALAXY'
        WHEN UPPER(V.PVNAMVEN) = 'TUBE & SOLID TIRE LIMITED' THEN 'CO-OP TUBES'
        WHEN UPPER(V.PVNAMVEN) = 'SHANE WAGONER' THEN '#N/A'
        WHEN UPPER(V.PVNAMVEN) = 'MITAS NORTH AMERICA' THEN 'MITAS'
        WHEN UPPER(V.PVNAMVEN) = 'SPECIALTY TIRES OF' THEN 'SPECIALTY TIRE OF AMERICA'
        WHEN UPPER(V.PVNAMVEN) = 'MCMAHON''S BEST-ONE TIRE' THEN 'RETREAD/BANDAG'
        WHEN UPPER(V.PVNAMVEN) = 'NEXEN TIRE AMERICAN INC' THEN 'NEXEN'
        WHEN UPPER(V.PVNAMVEN) = 'EAGLE TRUCK WASH' THEN 'NITTO'
        WHEN UPPER(V.PVNAMVEN) = 'YOKOHAMA OFF-HIGHWAY' THEN 'MILESTAR'
        WHEN UPPER(V.PVNAMVEN) = 'TOYO TIRE' THEN 'TOYO'
        WHEN UPPER(V.PVNAMVEN) = 'TURBO WHOLESALE TIRES' THEN 'LEXANI'
        WHEN UPPER(V.PVNAMVEN) = 'TRI-CITY FIRESTONE' THEN 'RBP'
        WHEN UPPER(V.PVNAMVEN) = 'SOUTHEASTERN COMMERCIAL' THEN 'LIONHART'
        WHEN UPPER(V.PVNAMVEN) = 'FLEET PRIDE' THEN 'DEESTONE'
        WHEN UPPER(V.PVNAMVEN) = 'AMERICAN OMNI TRADING CO' THEN 'THUNDERER'
        WHEN UPPER(V.PVNAMVEN) = 'MID US TIRE' THEN 'NOKIAN'
        WHEN UPPER(V.PVNAMVEN) = 'FASTENAL COMPANY' THEN 'IRONHEAD'
        WHEN UPPER(V.PVNAMVEN) = 'H & H WHOLESALE INC' THEN 'HIRUN'
        WHEN UPPER(V.PVNAMVEN) = 'MAXAM' THEN 'WOLFPACK'
        WHEN UPPER(V.PVNAMVEN) = 'CEAT' THEN 'CEAT'
        WHEN UPPER(V.PVNAMVEN) = 'CONSOLIDATED' THEN 'DOUBLE COIN'
        WHEN UPPER(V.PVNAMVEN) = 'FIRESTONE STORE' THEN '#N/A'
        WHEN UPPER(V.PVNAMVEN) = 'AMERICAN KENDA RUBBER' THEN 'KENDA'
        WHEN UPPER(V.PVNAMVEN) = 'BUCKEYE TIRE & SVC CO' THEN '#N/A'
        WHEN UPPER(V.PVNAMVEN) = 'VENOM' THEN 'VENOM'
        WHEN UPPER(V.PVNAMVEN) = 'PEP BOYS' THEN 'PREDATOR'
        WHEN UPPER(V.PVNAMVEN) = 'HAMATON INC' THEN '#N/A'
        WHEN UPPER(V.PVNAMVEN) = 'GROUP 31 INCORPORATED' THEN '#N/A'
        WHEN UPPER(V.PVNAMVEN) = 'VCT WHEEL' THEN '#N/A'
        WHEN UPPER(V.PVNAMVEN) = 'GREENFIELD FIRESTONE' THEN '#N/A'
        WHEN UPPER(V.PVNAMVEN) = 'AFFORDABLE ROOFING' THEN '#N/A'
        WHEN UPPER(V.PVNAMVEN) = 'DELPHA CHEV-BUICK-PONT-GE' THEN 'MISC AIRCRAFT TUBES'
        WHEN UPPER(V.PVNAMVEN) = 'HUBER TIRE INC' THEN 'COUNTRYWIDE TUBES'
        WHEN UPPER(V.PVNAMVEN) = 'DOUBLE A TRAILER' THEN 'UNVERFERTH MFG'
        WHEN UPPER(V.PVNAMVEN) = 'AETNA U.S. HEALTHCARE' THEN 'AWS INC'
        WHEN UPPER(V.PVNAMVEN) = 'LOCATION 8' THEN '#N/A'
        WHEN UPPER(V.PVNAMVEN) = 'OHIO TREASURER OF STATE' THEN 'SINGLE TUBES'
        WHEN UPPER(V.PVNAMVEN) = 'SIGN OUTLET' THEN '#N/A'
        WHEN UPPER(V.PVNAMVEN) = 'CFI TIRE AND WHEEL' THEN 'MISC TIRES & WHEELS'
        WHEN UPPER(V.PVNAMVEN) = 'LOCATION 9' THEN '#N/A'
        WHEN UPPER(V.PVNAMVEN) = 'ERECTORS II INC.' THEN 'KUHMO WALMART'
        ELSE V.PVNAMVEN
    END AS 'VENDOR NAME',

    T01.TIHLCLSPRD AS 'PRODUCT CLASS',
    T01.TIHLPRD AS 'PRODUCT CODE',
    T01.TIHLPRDDSC AS 'PRODUCT DESCRIPTION',
    T01.TIHLQTY AS 'QUANTITY',
    T01.TIHLNUMINV AS 'INVOICE #',
    T01.TIHLPRC AS 'PRICE',
    T03.TIHHDTEINV AS 'INVOICE DATE',
    T03.TIHHCLSCST AS 'CUSTOMER CLASS',
    T04.PDMIN AS 'MIN',
    T04.PDMAX AS 'MAX'

FROM DTA273.TMIHSH T03

STRAIGHT_JOIN DTA273.TMIHSL T01
    ON T01.TIHLNUMCST = T03.TIHHNUMCST
   AND T01.TIHLNUMINV = T03.TIHHNUMINV

LEFT JOIN (
    SELECT
        CUNUMBER,
        CUNAME,
        CUROUTECD
    FROM DTA273.TMCUST
) T02
    ON T02.CUNUMBER = T03.TIHHNUMCST

LEFT JOIN DTA273.TMPROD T04
    ON T04.PDNUMBER = T01.TIHLPRD
   AND T04.PDSTORE = 1

LEFT JOIN DTA273.PMVEND V
    ON V.PVNUMVEN = T04.PDVENDOR

WHERE T03.TIHHDTEINV BETWEEN
      DATE_FORMAT(
          DATE_SUB(CURDATE(), INTERVAL 1 MONTH),
          '%Y%m01'
      )
  AND DATE_FORMAT(
          LAST_DAY(DATE_SUB(CURDATE(), INTERVAL 1 MONTH)),
          '%Y%m%d'
      )

  AND T03.TIHHVOIDYN = 'N'

  AND T02.CUNAME IS NOT NULL
  AND T01.TIHLQTY <> 0
 	AND T04.PDVENDOR NOT IN (900, 851)
        AND TRIM(UPPER(T01.TIHLPRD)) NOT IN ('NSAP','NSBATT','NSEQ','BOX') 
  AND T01.TIHLADJYN IN ('N', ' ')
  AND T04.PDMIN = 0
  AND T04.PDMAX = 0

  AND T01.TIHLSLMSEL NOT IN (
      193,315,316,370,568,1170,1168,
      151,1211,1137,1129,1109,3014,
      3032,3029,3026,3033,3091,3000,
      2500,2108
  );