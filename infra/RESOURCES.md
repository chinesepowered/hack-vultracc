# Vultr resources (tieout)

Every create, resize and delete, with its hourly cost. All labels start with `tieout-`; instances and the database carry the tag `tieout`.

| Time (UTC) | Action | Kind | Label | ID | $/hour | Note |
|---|---|---|---|---|---|---|
| 2026-09-26 21:02 | create | VPC | tieout-vpc | `5e18f8f3-3dc5-43da-a551-a42951345add` | 0.0000 | sjc 10.66.0.0/24, private network between control plane and sandbox hosts |
| 2026-09-26 21:03 | create | Firewall group | tieout-cp-fw | `83ff8d04-6747-4b98-9cb0-b4e300e5b522` | 0.0000 | inbound rules: http (ACME + redirect), https |
| 2026-09-26 21:03 | create | Firewall group | tieout-sbx-fw | `ea9f33af-30c1-4863-b476-12c04272c23d` | 0.0000 | inbound rules: none (all inbound dropped) |
| 2026-09-26 21:03 | create | Object Storage | tieout-objects | `edde9df8-f5bc-4355-a3e2-d29f5036b28b` | 0.0082 | cluster sjc1.vultrobjects.com tier 6 |
| 2026-09-26 21:04 | create | Bucket | tieout-artifacts-4f2389 | `tieout-artifacts-4f2389` | 0.0000 | private; artifacts under clients/{client}/runs/{run}/ |
| 2026-09-26 23:39 | create | Instance | tieout-cp | `e7c2d87e-5e74-4189-b82f-ca887af64616` | 0.0274 | vc2-2c-4gb (2 vCPU, 4096 MB), Ubuntu 24.04, role all |
| 2026-09-26 23:39 | create | Instance | tieout-sbx-1 | `ce80a289-4137-42a4-bbe6-248ad57dee74` | 0.0548 | vc2-4c-8gb (4 vCPU, 8192 MB), Ubuntu 24.04, role sandbox |
| 2026-09-26 23:39 | create | Managed PostgreSQL | tieout-pg | `1b79ba58-90dc-492a-9a27-2fa3bfd14de4` | 0.0411 | plan vultr-dbaas-startup-cc-1-55-2, pg 16 |
| 2026-09-27 03:08 | create | Instance | tieout-sbx-2 | `bd2e9cc2-bc82-4b94-b102-be4ee47206a7` | 0.0548 | vc2-4c-8gb (4 vCPU, 8192 MB), Ubuntu 24.04, role sandbox |
| 2026-09-28 00:07 | delete | Instance | tieout-cp | `e7c2d87e-5e74-4189-b82f-ca887af64616` | 0.0274 | teardown after the hackathon; billing stops |
| 2026-09-28 00:07 | delete | Instance | tieout-sbx-1 | `ce80a289-4137-42a4-bbe6-248ad57dee74` | 0.0548 | teardown after the hackathon; billing stops |
| 2026-09-28 00:07 | delete | Instance | tieout-sbx-2 | `bd2e9cc2-bc82-4b94-b102-be4ee47206a7` | 0.0548 | teardown after the hackathon; billing stops |
| 2026-09-28 00:07 | delete | Managed PostgreSQL | tieout-pg | `1b79ba58-90dc-492a-9a27-2fa3bfd14de4` | 0.0411 | teardown after the hackathon; billing stops |
| 2026-09-28 00:07 | delete | Object Storage | tieout-objects | `edde9df8-f5bc-4355-a3e2-d29f5036b28b` | 0.0082 | teardown after the hackathon; billing stops |
| 2026-09-28 00:07 | delete | Firewall group | tieout-sbx-fw | `ea9f33af-30c1-4863-b476-12c04272c23d` | 0.0000 | teardown after the hackathon; billing stops |
| 2026-09-28 00:08 | delete | Firewall group | tieout-cp-fw | `83ff8d04-6747-4b98-9cb0-b4e300e5b522` | 0.0000 | teardown after the hackathon; billing stops |
| 2026-09-28 00:08 | delete | VPC | tieout-vpc | `5e18f8f3-3dc5-43da-a551-a42951345add` | 0.0000 | teardown after the hackathon; billing stops |
