import { z } from 'zod'

export const MODEL_OUTPUT_BYTES = 69_000
export const modelCatalogReply = z.strictObject({
  status: z.literal('ok'),
  models: z.array(z.string().regex(/^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$/u)).max(512),
  truncated: z.boolean(),
})
