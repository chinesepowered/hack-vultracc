# Vultr resources (tieout)

Every create, resize and delete, with its hourly cost. All labels start with `tieout-`; instances and the database carry the tag `tieout`.

| Time (UTC) | Action | Kind | Label | ID | $/hour | Note |
|---|---|---|---|---|---|---|
| 2026-09-26 21:02 | create | VPC | tieout-vpc | `5e18f8f3-3dc5-43da-a551-a42951345add` | 0.0000 | sjc 10.66.0.0/24, private network between control plane and sandbox hosts |
| 2026-09-26 21:03 | create | Firewall group | tieout-cp-fw | `83ff8d04-6747-4b98-9cb0-b4e300e5b522` | 0.0000 | inbound rules: http (ACME + redirect), https |
| 2026-09-26 21:03 | create | Firewall group | tieout-sbx-fw | `ea9f33af-30c1-4863-b476-12c04272c23d` | 0.0000 | inbound rules: none (all inbound dropped) |
| 2026-09-26 21:03 | create | Object Storage | tieout-objects | `edde9df8-f5bc-4355-a3e2-d29f5036b28b` | 0.0082 | cluster sjc1.vultrobjects.com tier 6 |
| 2026-09-26 21:04 | create | Bucket | tieout-artifacts-4f2389 | `tieout-artifacts-4f2389` | 0.0000 | private; artifacts under clients/{client}/runs/{run}/ |
