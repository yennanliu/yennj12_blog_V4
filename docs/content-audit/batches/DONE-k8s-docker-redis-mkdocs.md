# DONE-k8s-docker-redis-mkdocs — kubernetes-complete-guide ×3, docker-complete-guide ×3, docker-mount, mkdocs, redis-sentinel

Reviewed 2026-10-03 (parallel pass). 9 posts: 1 Ready / 5 Needs revision / 3 Not ready.

## Per-post scorecard

| file | lines | A | C | D | V | S | F | Overall | Verdict | top finding |
|---|---|---|---|---|---|---|---|---|---|---|
| kubernetes-complete-guide-part1-introduction-zh.md | 1011 | 3 | 4 | 2 | 3 | 3 | 4 | 3.2 | Needs revision | No thesis; feature-list survey. L635-637 recommends `kubectl get componentstatuses` (deprecated since 1.19); L892 links Katacoda (shut down 2022). |
| kubernetes-complete-guide-part2-resources-zh.md | 1487 | 3 | 4 | 2 | 3 | 3 | 4 | 3.2 | Needs revision | No thesis; YAML/kubectl reference. L507 `--record` (deprecated), L612 tolerates `node-role.kubernetes.io/master` (renamed `control-plane` in 1.24), L1045 `provisioner: kubernetes.io/aws-ebs` (in-tree driver removed; should be `ebs.csi.aws.com`). |
| kubernetes-complete-guide-part3-advanced-zh.md | 1723 | 3 | 3 | 2 | 3 | 3 | 4 | 3.0 | Needs revision | L620-638 "allow DNS" NetworkPolicy lists `namespaceSelector` and `podSelector` as separate `to:` items — an OR, contradicting the correctly-ANDed form at L559-565. |
| docker-complete-guide-part1-introduction-zh.md | 958 | 3 | 4 | 2 | 3 | 3 | 4 | 3.2 | Needs revision | No thesis. Install section stale: L414 "VirtualBox 或 HyperKit", L417 Windows Pro-only, L548-549 dead mirror `registry.docker-cn.com`, L561 obsolete `overlay2.override_kernel_check`. |
| docker-complete-guide-part2-commands-zh.md | 1363 | 3 | 4 | 2 | 2 | 3 | 4 | 3.0 | Needs revision | Pure command reference, no thesis. L626 and L1207 `docker scan` — removed 2023 (Docker Desktop 4.17), replaced by `docker scout cves`. |
| docker-complete-guide-part3-advanced-zh.md | 1587 | 2 | 4 | 3 | 3 | 3 | 4 | 3.2 | Not ready | L1155-1170 "主從複製" uses Bitnami env vars (`POSTGRES_REPLICATION_MODE`, `POSTGRES_MASTER_HOST`) on the official `postgres:15` image — ignored, so the "HA" config produces two unrelated standalone DBs. |
| docker-mount-complete-guide-comparison.md | 1390 | 2 | 4 | 3 | 3 | 4 | 4 | 3.3 | Not ready | L483-484 SELinux labels swapped: `:z` is shared, `:Z` is private (post says the opposite). L463 default propagation is `rprivate`, not shared; L903 `--userns-remap` is a daemon flag. |
| mkdocs-site-size-deploy-perf-tuning-zh.md | 411 | 4 | 5 | 4 | 3 | 5 | 4 | 4.2 | Ready | Best post in the group: real thesis, dated PR, why-X-not-Y with flip conditions, all percentages recompute. Minor: L37 "5,000 頁 × 1MB" vs 3.1 GB total (L32) never reconciled. |
| redis-sentinel-high-availability-setup-guide.md | 1751 | 2 | 3 | 3 | 3 | 3 | 4 | 3.0 | Not ready | L211 conflates quorum (ODOWN detection) with the majority vote needed for failover; never explains `min-replicas-to-write` or split-brain. Java does not compile (Micrometer `Counter.increment(Tags)`, `redisOperationTimer.builder()`); `spring.redis.*` keys silently ignored on Spring Boot 3. |

## Patterns
- **Content quality — twin templates, same voice.** The docker and k8s zh guides are the same scaffold with different nouns: identical 🎯 前言 + 系列規劃 block (docker p1 L13-20 / k8s p1 L13-20), identical closing 核心知識回顧 → 檢查清單 → 學習資源推薦 → 🎉 結語 → 祝您…🚀 (docker p3 L1447-1587 / k8s p3 L1628-1724), identical six-stage 學習路徑 mermaid, identical Q1..Q5 FAQ tables. Six posts, zero theses. Simplified-Chinese vocabulary leaks into 繁體 posts (k8s p2 L370 "数据库").
- **Visuals — Mermaid as decoration.** k8s p1 has 14 diagrams; most are radial feature lists (L28-51, L370-393, L751-769) or boxes containing bullet text (docker p1 L759-793). The informative ones (k8s p1 L213-236 sequence, docker p1 L611-629, docker-mount L792-812 decision tree) are the minority.
- **Depth — "complete guide" = reference dump.** docker p2 (1363 lines) is a man page; k8s p2 is a 160-line Pod spec with every field commented. No post answers "when does this break": no HPA/VPA conflict in k8s p3, no split-brain in redis, no I/O numbers in docker-mount (star ratings at L777-783 instead).
- **Direction — overlap with kubernetes-autoscaling series.** k8s p3 L47-231 echoes autoscaling part1 L220-228 and part5; k8s p3 L1044-1067 duplicates autoscaling part4's kube-prometheus-stack install. Neither series links to the other.
- **Accuracy — point patches on a stale base.** Good 2026 notes (ingress-nginx retirement k8s p2 L851, VirtioFS docker-mount L441, Redis address trap L400, BuildKit default docker p3 L992) sit next to 2023-era content (`controller-v1.8.1` k8s p2 L984, `docker scan` ×3, `helm repo add stable` k8s p3 L945, `actions/checkout@v3`).
- **Format.** Descriptions describe scope not payoff; only mkdocs sells a result. `weight:` set correctly on both series. k8s p3 mixes zh and en tags. redis readTime 29 min for 1751 lines (~55 min).

## Verified / unverified claims (abridged)
- ✅ k8s p1 L133/L209 dockershim removal 1.24; ✅ k8s p2 L851 ingress-nginx retirement March 2026; ✅ `autoscaling/v2`, `networking.k8s.io/v1`, `batch/v1` CronJob `timeZone`, `ReadWriteOncePod` current.
- ❌ k8s p1 L635 componentstatuses; L892 Katacoda. ❌ k8s p2 L507 `--record`; L612 master taint; L1045 aws-ebs in-tree. ❌ k8s p3 L620-638 NetworkPolicy OR/AND; L945 helm stable; ⚠️ L1119-1127 CPU alert unit mismatch (cores rendered as a percentage). ❓ L171 VPA `Auto` described as in-place (historically Recreate; in-place is `InPlaceOrRecreate`).
- ❌ docker p1 L414/L417/L548/L561 stale; ❓ L120/L125 overhead and density figures unsourced. ✅ docker p2 L1086 Compose V1 EOL 2023; ❌ L626/L1207 `docker scan`. ❌ docker p3 L1155-1170 Bitnami vars; L933 `--link`; L1307/L1330 `docker/compose:latest` (V1 image) in a post that declares V1 dead; ⚠️ L1122-1178 Swarm-only keys under "高可用性配置" without saying compose ignores them. ✅ L441-444 −98.75 % recomputes.
- ❌ docker-mount L483-484 z/Z swapped; L463 propagation default; L903 userns-remap flag. ✅ L441 VirtioFS note; ✅ L697 tmpfs not shareable.
- ✅ mkdocs L376-386 nine percentages recompute; L297 −30.7 %. ⚠️ L37 vs L32 vs L383 size figures unreconciled.
- ❌ redis L211 quorum vs majority; ❌ L494-513 `spring.redis.*` on Boot 3; ❌ L700/L707 ×14 Micrometer API misuse; ❌ L1454-1480 Gauge re-registration no-op, Counter over-count; ⚠️ L974 connection leak; L249 `version: '3.8'` obsolete. ✅ L400-403 Docker address-trap warning and `announce-ip` fix.

## Recommendations
1. **Merge the two k8s series or cross-link them** — the complete-guide p3 autoscaling section is a thinner copy of the autoscaling series; replace it with a summary + link.
2. **Fix the five wrong-as-written items first** (NetworkPolicy OR/AND, Bitnami env vars on official postgres, SELinux z/Z, redis quorum vs majority, Spring Boot 3 property keys) — readers will copy these.
3. **Sweep stale commands** (`docker scan`, `componentstatuses`, `--record`, helm stable, in-tree aws-ebs, `actions/*@v3`) with a dated "as of" line at the top of each guide.
4. **Give each "complete guide" a thesis and a "when it breaks" section**; cut the FAQ/checklist/motivational closers that are copy-pasted across both series.
5. **Replace feature-list Mermaid with 1–2 mechanism diagrams per post.**
