# Field notes

(Part 2 of the manual: at least five things you noticed inside WordPress Playground, in your own words.)

1. Playground drops you straight into the admin dashboard as "Howdy, admin" — no login screen, no password. You're just already an admin with full edit rights over the whole site. That's the opposite of what MP2 wants: my CMS has to make you actually authenticate before you can touch anything.

2. I poked around the checkout/coupon area (this is a WooCommerce demo, not core WordPress, so not directly one of my 7 capabilities) and found a real bug: I applied a coupon at checkout and it said "applied" successfully, but the price didn't actually go down. The discount logic and the UI confirmation aren't actually wired together — the interface lied about what happened. Good reminder to actually test that my own "success" messages correspond to something real changing in the database, not just a toast notification.

(need 3+ more — still to do: draft vs. published visibility, page vs. post navigation placement, slug generation, Editor role restriction on Users, status filter on the post list)
