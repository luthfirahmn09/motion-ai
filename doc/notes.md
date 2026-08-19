FPSX9c82b65e832f41b1b1e18c809da88cc5


UPDATE users
SET subscription_status = 'active',
    subscription_expires_at = NOW() + INTERVAL '14 days'
WHERE id = 5035158595;
