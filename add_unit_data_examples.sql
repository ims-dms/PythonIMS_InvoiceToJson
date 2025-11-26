-- SQL Script to Add Unit Conversion Data to MULTIALTUNIT Table
-- ================================================================

-- Example: Adding unit data for Kingfisher Strong Beer products
-- Adjust the values based on your actual packaging

-- Kingfisher Strong Beer 650ML Bottle
INSERT INTO MULTIALTUNIT (mcode, BASEUOM, CONFACTOR, altunit)
VALUES ('M44493P', 'Pcs', 12, 'Case');

-- Nescafe Gold Rich Aroma Coffee 50GR Jar
INSERT INTO MULTIALTUNIT (mcode, BASEUOM, CONFACTOR, altunit)
VALUES ('MHOO6152', 'Pcs', 12, 'Case');

-- Note: You may need to check the exact structure of your MULTIALTUNIT table
-- Run this query first to see the table structure:
-- EXEC sp_help 'MULTIALTUNIT'

-- To add unit data in bulk for multiple products, you can use:
/*
INSERT INTO MULTIALTUNIT (mcode, BASEUOM, CONFACTOR, altunit)
VALUES 
    ('M44493P', 'Pcs', 12, 'Case'),
    ('MHOO6152', 'Pcs', 12, 'Case'),
    ('MCODE3', 'Pcs', 24, 'Case'),
    ('MCODE4', 'Kg', 10, 'Box');
*/

-- To check if data was added successfully:
SELECT m.desca, m.mcode, a.BASEUOM, a.CONFACTOR, a.altunit
FROM menuitem m
INNER JOIN MULTIALTUNIT a ON m.mcode = a.mcode
WHERE m.mcode IN ('M44493P', 'MHOO6152');
