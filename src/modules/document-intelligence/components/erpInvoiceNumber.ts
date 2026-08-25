export const ERP_INVOICE_RULE_VERSION = (
  'erp-invoice-number-admission@1.2.0'
)
export const NO_REMITTANCE_INVOICE = '9999999999'

const ERP_INVOICE_NUMBER = /^\d{8,9}$/

export function normalizeErpInvoiceNumber(value: unknown): string {
  const digits = String(value ?? '').replace(/\D/g, '')
  if (
    !ERP_INVOICE_NUMBER.test(digits)
    || digits === NO_REMITTANCE_INVOICE
  ) {
    return ''
  }
  return digits
}

export function isValidErpInvoiceNumber(value: unknown): boolean {
  return Boolean(normalizeErpInvoiceNumber(value))
}
