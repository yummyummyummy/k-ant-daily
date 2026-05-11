-- PIN-based login support — add nullable columns to members.
--
-- Run after deploying with the new code:
--   wrangler d1 execute k-ant-game --file=migrations/0002_member_pin.sql --remote
--
-- Existing claimed members (token set, pin_hash NULL) keep working via
-- their URL token; they are prompted to set a PIN on next visit.

ALTER TABLE members ADD COLUMN pin_hash TEXT;
ALTER TABLE members ADD COLUMN pin_set_at INTEGER;
