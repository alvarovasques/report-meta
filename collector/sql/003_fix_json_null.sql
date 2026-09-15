-- 003: linhas gravadas com JSON null (em vez de NULL SQL) em actions/cost_per_action quebravam jsonb_array_elements
UPDATE meta.ads_daily SET actions = NULL WHERE actions IS NOT NULL AND jsonb_typeof(actions) <> 'array';
UPDATE meta.ads_daily SET cost_per_action = NULL WHERE cost_per_action IS NOT NULL AND jsonb_typeof(cost_per_action) <> 'array';
