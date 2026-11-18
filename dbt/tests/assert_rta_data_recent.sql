{{ config(severity = 'warn') }}
-- RTA publishes about a month after each quarter ends, so the latest quarter should be under
-- ~200 days old. A warning, not an error: an RTA delay is not a data-quality failure, and the
-- CI fixture's dates are fixed.
select max(quarter_end) as latest_quarter, current_date - max(quarter_end) as days_old
from {{ ref('stg_rta__bond_stats') }}
having current_date - max(quarter_end) > 200
