"""One owner-approved code package. No model, private source writes or queue editor.

The native source controller selects/verifies the immutable Work and preserves
the original scheduler, credential validator and native Result channel.
"""
import base64
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request

from orchestrator_code_lease import (
    SOURCE, PUBLIC, SOURCE_ID, PUBLIC_ID, OWNER_ID, PAID, CODE, LEASE,
    TTL_SECONDS, require, unique, checked_run, created_at, public_parent, source_parent,
    force_off, read_gate,
)

BRANCH = "feature/emergency-close-persistence"
CONTROLLER = "orchestrator-code-controller.yml"
WATCHDOG = "one-shot-gateway.yml"
ORIGINAL_MARKER = "cw-issue129-code-package-consumed"
RECOVERY1_MARKER = "cw-issue129-code-recovery1-consumed"
RECOVERY2_MARKER = "cw-issue129-code-recovery2-consumed"
MARKER = "cw-issue129-code-recovery3-consumed"
ACCELERATED_MARKER = "cw-issue129-accelerated1-consumed"
ACCELERATED_WORK = "c0aee570e2be1974a8290b7e959ec3c7fc2944d2a3abf8452a7f650773b87a7b"
ACCELERATED_PACKAGE = "issue129-20261022-accelerated"
ACCELERATED2_MARKER = "cw-issue129-accelerated2-consumed"
ACCELERATED2_WORK = "e1a5eaaa15985deeede5a2212dc59defc856c0c6ee6697d2b50f26656c731c7f"
ACCELERATED3_MARKER = "cw-issue129-accelerated3-consumed"
ACCELERATED3_WORK = "ab29e0a8ab0d09f9f37baa43332a58ab27957e80cb41920f32b98b58f5bd48fd"
ACCELERATED4_MARKER = "cw-issue129-accelerated4-consumed"
ACCELERATED4_WORK = "7ab4624b2453ff8dbf301193e86d8e578a157e23cfcb5a71c7ce6d7095f2deb0"
ACCELERATED5_MARKER = "cw-issue129-accelerated5-consumed"
ACCELERATED5_WORK = "60578e469bef7b76fddbdbbe84485fbd3c22bffd215e2337f6e7281ca49357c0"
ACCELERATED6_MARKER = "cw-issue129-accelerated6-consumed"
ACCELERATED6_WORK = "f03bec47b327a7180c8a6cf3daf9b3c3dd570dbfa37885236ea3876791143c2f"
ACCELERATED7_MARKER = "cw-issue129-accelerated7-consumed"
ACCELERATED7_WORK = "5f2018a617438ae4c19a241b7b57ee4d175cd83e146fedf525fb53f237dd1b13"
ACCELERATED8_MARKER = "cw-issue129-accelerated8-consumed"
ACCELERATED8_WORK = "adcabbc143966275839e910937b4ac30cbf90791415e9ae2d5c2ac63d171b038"
ACCELERATED7_SOURCE = "d87fbca27ad41a3f3fc87cf79c1b0a0283cbe785"
ACCELERATED7_PUBLIC = "88e8dfea7f466dd7b2311ddf6bae3f582dac7ea4"
RETAINED_ACCELERATED8_HEAD = "5ee303763ee337682135c96ed610d421c2776a19"
RETAINED_ACCELERATED8_SHA256 = "35f5827eab3cc8499bebb0cb626bc5c912456560227d1ea6e44dabc4e1a84f53"
ACCELERATED6_SOURCE = "903ccb8c202485a986fc95665a10c5141095fffa"
ACCELERATED6_PUBLIC = "8180c74aba103eb45f88a765772d69fab08b24a8"
RETAINED_ACCELERATED7_HEAD = "a0be4d096c7f290d7bcaf67e31f51451cd1826b0"
RETAINED_ACCELERATED7_SHA256 = "cef9d67e9625c868695b295e78c3d1b8e1c5731303f7a69c8a9933826c1e0314"
ACCELERATED5_SOURCE = "45d7d14ed4825e8e4048261b0c4ef8f03b9c718b"
ACCELERATED5_PUBLIC = "df12cc9ec9c58d44966adaa764f2574543b4093f"
RETAINED_ACCELERATED6_HEAD = "2556eb92b5aadc105ed9984f2da3c20939bf6d81"
RETAINED_ACCELERATED6_SHA256 = "ca07fe94be18bcd1c2e416d03d09636bcfd74f274cca40acdea01b5bfb2d88bb"
ACCELERATED4_SOURCE = "6e99bcce50019e887c10597d315e0cc2d27aff6e"
ACCELERATED4_PUBLIC = "c1538fc491b19d085fc88685ced06c0fbb9bc49b"
RETAINED_ACCELERATED5_HEAD = "825ab5d5c5eddac6e56b245c49d9b37d9b6e8f4c"
RETAINED_ACCELERATED5_SHA256 = "8a57d4c23d7619b94edc286fb78a123ae86fe3a0400234cdae90345847f733c2"
ACCELERATED3_SOURCE = "ed3c9d3c78afc3b97e1ec755617f96b09377d870"
ACCELERATED3_PUBLIC = "6138cfb6cb1180f3bd31a559588648f5e0cc18f9"
RETAINED_ACCELERATED_HEAD = "26936196b6b690dc5ac7542b4377541d3c62b315"
RETAINED_ACCELERATED_SHA256 = "9018aa21eac61277c9628faaabd72b1ee2fdb1a4e497f44e4da2fe31e60b5f41"
ACCELERATED2_SOURCE = "c7be289a11f899dee96f0d5f2fbe9c400ac5753f"
ACCELERATED2_PUBLIC = "e34d59c9932bdef5e7b62924b8159a5eaadc5fb4"
ACCELERATED1_SOURCE = "dbaf880be664a82b93cbb2551fb5ba6de88a580d"
ACCELERATED1_PUBLIC = "1888cdd02994853cffb31204dab0d90506ae3ead"
RETAINED_FINAL_HEAD = "b8d2bec4e8df01ba6cab64e2a4175b863164dac3"
RECOVERY3_SOURCE = "37d3843ad1383f85739a68735133d0125bcbe6ba"
RECOVERY3_PUBLIC = "1219d1ef32b38db3f0b453fe96c9fda2c9777891"
ORIGINAL_PUBLIC_SHA = "ca40f15b187935a7ed001b161a9fae4263cd55e0"
ORIGINAL_SOURCE_SHA = "0ce91af5f558942e271d06416eb14ded9a99142a"
ORIGINAL_WORK_ID = "ba394f0b88edbc372f360496990d02fa77b8d33f587ec9f051a20822b1249c1c"
RECOVERY1_WORK_ID = "078fc14324d2bbd501e38c8b6641e0f1f4ae0bac6ada8db0d63f9a996e391691"
RECOVERY1_PUBLIC_SHA = "0bd469c8586ec3d05ee06ee9c1fe56d4cc8cc877"
RECOVERY1_SOURCE_SHA = "c016d16a2f5ee01d7d8dba169c663ca5f030724f"
RECOVERY2_WORK_ID = "df442f6a440d52a3533ccbda0c20671ab54259f54ff481b5cfba2970594b88c5"
RECOVERY2_PUBLIC_SHA = "1ca08eb07be09f76faf8842871e4d8ee6e266367"
RECOVERY2_SOURCE_SHA = "127512bb78dfbbf79746a7f14ca905a74ecc516f"
RECOVERY_WORK_ID = "7761f5c0e74aaec872633668c85e04b4d0e50469745a10dc2d79475eb54edc16"
RETAINED_BUDGET_SHA256 = "fdfe7fa44a9937d3dee0c566cb1d720f2df5a4ff91c2573762b537fae1eacd19"
LIVE = ("requested", "queued", "in_progress", "waiting", "pending")
# GitHub's bounded 50-run listing includes repository/user metadata per row.
# Keep a finite byte ceiling while allowing the real listing (~700 KiB).
MAX_API_RESPONSE_BYTES = 2 * 1024 * 1024


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("CODE_GATEWAY_REDIRECT_DENIED")


def api(repository, method, path, token, body=None):
    require(repository in (SOURCE, PUBLIC) and method in ("GET", "POST", "PATCH")
            and type(path) is str and not any(x in path for x in ("..", "#", "\\"))
            and type(token) is str and 15 <= len(token) <= 16384)
    if method != "GET":
        allowed = (
            repository == SOURCE and method == "PATCH" and path in tuple("actions/variables/" + x for x in (PAID, CODE, LEASE))
            or repository == SOURCE and method == "POST" and path in ("actions/variables", "actions/workflows/" + CONTROLLER + "/dispatches")
            or repository == PUBLIC and method == "POST" and path in ("git/refs", "actions/workflows/" + WATCHDOG + "/dispatches")
        )
        require(allowed)
    request = urllib.request.Request("https://api.github.com/repos/" + repository + ("/" + path if path else ""),
        data=None if body is None else json.dumps(body, separators=(",", ":")).encode(), method=method,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
            "Content-Type": "application/json", "Cache-Control": "no-cache",
            "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "cw-issue129-code-gateway"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=12) as response:
            require(response.status in (200, 201, 204))
            raw = response.read(MAX_API_RESPONSE_BYTES + 1)
            require(len(raw) <= MAX_API_RESPONSE_BYTES)
            return json.loads(raw, object_pairs_hook=unique) if raw.strip() else None
    except urllib.error.HTTPError as exc:
        if method == "GET" and exc.code == 404:
            return None
        # Never echo the response, URL, credential, or exception text.
        if type(exc.code) is int and 100 <= exc.code <= 599:
            print("CODE_GATEWAY_HTTP_ERROR_" + str(exc.code), flush=True)
        raise ValueError("CODE_GATEWAY_OUTCOME_UNKNOWN_NO_RETRY") from None
    except Exception:
        raise ValueError("CODE_GATEWAY_OUTCOME_UNKNOWN_NO_RETRY") from None


def context(environment):
    expected = {"GITHUB_REPOSITORY": PUBLIC, "GITHUB_REPOSITORY_ID": str(PUBLIC_ID),
        "GITHUB_REF": "refs/heads/main", "GITHUB_EVENT_NAME": "workflow_dispatch",
        "GITHUB_ACTOR": "1978serg-cpu", "GITHUB_ACTOR_ID": str(OWNER_ID), "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_WORKFLOW_REF": PUBLIC + "/.github/workflows/code-gateway.yml@refs/heads/main"}
    require(all(environment.get(name) == value for name, value in expected.items()))
    values = {name: environment.get(name, "") for name in ("GITHUB_SHA", "CW_SOURCE_SHA", "CW_WORK_ID", "GITHUB_RUN_ID")}
    for name in ("GITHUB_SHA", "CW_SOURCE_SHA"):
        require(re.fullmatch("[a-f0-9]{40}", values[name]))
    require(re.fullmatch("[a-f0-9]{64}", values["CW_WORK_ID"])
            and values["CW_WORK_ID"] in (RECOVERY_WORK_ID, ACCELERATED_WORK, ACCELERATED2_WORK, ACCELERATED3_WORK, ACCELERATED4_WORK, ACCELERATED5_WORK, ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK)
            and values["CW_SOURCE_SHA"] not in (ORIGINAL_SOURCE_SHA, RECOVERY1_SOURCE_SHA, RECOVERY2_SOURCE_SHA)
            and re.fullmatch("[1-9][0-9]{0,19}", values["GITHUB_RUN_ID"]))
    if values["CW_WORK_ID"] in (ACCELERATED_WORK, ACCELERATED2_WORK, ACCELERATED3_WORK, ACCELERATED4_WORK, ACCELERATED5_WORK, ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK):
        require(values["CW_SOURCE_SHA"] != RECOVERY3_SOURCE)
    if values["CW_WORK_ID"] in (ACCELERATED2_WORK, ACCELERATED3_WORK, ACCELERATED4_WORK, ACCELERATED5_WORK, ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK):
        require(values["CW_SOURCE_SHA"] != ACCELERATED1_SOURCE)
    if values["CW_WORK_ID"] in (ACCELERATED3_WORK, ACCELERATED4_WORK, ACCELERATED5_WORK, ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK):
        require(values["CW_SOURCE_SHA"] != ACCELERATED2_SOURCE)
    if values["CW_WORK_ID"] in (ACCELERATED4_WORK, ACCELERATED5_WORK, ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK):
        require(values["CW_SOURCE_SHA"] != ACCELERATED3_SOURCE)
    if values["CW_WORK_ID"] in (ACCELERATED5_WORK, ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK):
        require(values["CW_SOURCE_SHA"] != ACCELERATED4_SOURCE)
    if values["CW_WORK_ID"] in (ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK):
        require(values["CW_SOURCE_SHA"] != ACCELERATED5_SOURCE)
    if values["CW_WORK_ID"] in (ACCELERATED7_WORK, ACCELERATED8_WORK):
        require(values["CW_SOURCE_SHA"] != ACCELERATED6_SOURCE)
    if values["CW_WORK_ID"] == ACCELERATED8_WORK:
        require(values["CW_SOURCE_SHA"] != ACCELERATED7_SOURCE)
    return values


def rows(document, name):
    require(type(document) is dict and type(document.get(name)) is list and len(document[name]) <= 50)
    return document[name]


def source_preflight(call, token, source_sha, *, accelerated=False, continuation=False, fifth=False, sixth=False, seventh=False, eighth=False):
    print("CODE_GATEWAY_READ_SOURCE_IDENTITY", flush=True)
    repository = call(SOURCE, "GET", "", token)
    require(repository.get("full_name") == SOURCE and repository.get("id") == SOURCE_ID
            and repository.get("default_branch") == BRANCH)
    print("CODE_GATEWAY_READ_SOURCE_HEAD", flush=True)
    tip = call(SOURCE, "GET", "git/ref/heads/" + BRANCH, token)
    require(tip.get("object", {}).get("sha") == source_sha)
    print("CODE_GATEWAY_READ_BOTH_OFF_FLAGS", flush=True)
    require(all(read_gate(call, token, name) == "false" for name in (PAID, CODE)))
    print("CODE_GATEWAY_READ_RETAINED_PACKAGE_BUDGET", flush=True)
    if accelerated:
        retained = call(SOURCE, "GET", "git/ref/heads/cw-issue129-budget", token)
        require(retained.get("ref") == "refs/heads/cw-issue129-budget"
                and retained.get("object", {}).get("sha") == RETAINED_FINAL_HEAD)
    file = call(SOURCE, "GET", "contents/package-budget.json?ref="
                + ("cw-issue129-accelerated-budget" if accelerated else "cw-issue129-budget"), token)
    require(file.get("type") == "file" and file.get("encoding") == "base64" and file.get("size", 999999) <= 65536)
    budget = json.loads(base64.b64decode(file["content"], validate=False), object_pairs_hook=unique)
    if accelerated and continuation:
        require(hashlib.sha256(json.dumps(budget, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
                == (RETAINED_ACCELERATED8_SHA256 if eighth else RETAINED_ACCELERATED7_SHA256 if seventh else RETAINED_ACCELERATED6_SHA256 if sixth else RETAINED_ACCELERATED5_SHA256 if fifth else RETAINED_ACCELERATED_SHA256))
        tip = call(SOURCE, "GET", "git/ref/heads/cw-issue129-accelerated-budget", token)
        require(tip.get("ref") == "refs/heads/cw-issue129-accelerated-budget"
                and tip.get("object", {}).get("sha") == (RETAINED_ACCELERATED8_HEAD if eighth else RETAINED_ACCELERATED7_HEAD if seventh else RETAINED_ACCELERATED6_HEAD if sixth else RETAINED_ACCELERATED5_HEAD if fifth else RETAINED_ACCELERATED_HEAD))
    elif accelerated:
        require(type(budget) is dict and set(budget) == {"version", "package", "cap_cents", "max_requests",
            "revision", "transition_id", "entries"} and type(budget["version"]) is int and budget["version"] == 2
            and budget["package"] == ACCELERATED_PACKAGE and type(budget["cap_cents"]) is int and budget["cap_cents"] == 5000
            and type(budget["max_requests"]) is int and budget["max_requests"] == 100
            and type(budget["revision"]) is int and budget["revision"] == 0 and budget["entries"] == []
            and type(budget["transition_id"]) is str and re.fullmatch("[a-f0-9]{32}", budget["transition_id"]))
    else:
        require(hashlib.sha256(json.dumps(budget, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
                == RETAINED_BUDGET_SHA256)
    for workflow in (CONTROLLER, "gh-aw-code-worker.lock.yml", "gh-aw-worker-probe.lock.yml", "gh-aw-dispatcher-probe.lock.yml"):
        print("CODE_GATEWAY_CHECK_IDLE_" + workflow.replace(".yml", "").replace(".lock", "").replace("-", "_").upper(), flush=True)
        history = rows(call(SOURCE, "GET", "actions/workflows/" + workflow + "/runs?per_page=50", token), "workflow_runs")
        require(not any(run.get("status") in LIVE for run in history))


def predecessor(call, source_token, public_token, *, accelerated=False, successor=False, third=False, fourth=False, fifth=False, sixth=False, seventh=False, eighth=False):
    """Read positive terminal evidence; retain all three consumed attempt markers.

    The source controller independently authenticates the cancelled Claim and
    native Release before allowing the distinct successor Work to launch.
    source_preflight requires the exact seven-request $10/10 ledger, including
    its CONSUMED/unknown outcome. Nothing refunds or replays that old request.
    """
    marker = call(PUBLIC, "GET", "git/ref/heads/" + ORIGINAL_MARKER, public_token)
    require(type(marker) is dict and marker.get("ref") == "refs/heads/" + ORIGINAL_MARKER
            and marker.get("object", {}).get("sha") == ORIGINAL_PUBLIC_SHA)
    marker = call(PUBLIC, "GET", "git/ref/heads/" + RECOVERY1_MARKER, public_token)
    require(type(marker) is dict and marker.get("ref") == "refs/heads/" + RECOVERY1_MARKER
            and marker.get("object", {}).get("sha") == RECOVERY1_PUBLIC_SHA)
    marker = call(PUBLIC, "GET", "git/ref/heads/" + RECOVERY2_MARKER, public_token)
    require(type(marker) is dict and marker.get("ref") == "refs/heads/" + RECOVERY2_MARKER
            and marker.get("object", {}).get("sha") == RECOVERY2_PUBLIC_SHA)
    expected = (
        (PUBLIC, PUBLIC_ID, public_token, "39840999602", ORIGINAL_PUBLIC_SHA, "main", "code-gateway.yml", OWNER_ID,
         "CW issue129 code " + ORIGINAL_WORK_ID),
        (SOURCE, SOURCE_ID, source_token, "39841115852", ORIGINAL_SOURCE_SHA, BRANCH, CONTROLLER, OWNER_ID,
         "CW issue129 launch " + ORIGINAL_WORK_ID),
        (SOURCE, SOURCE_ID, source_token, "39841262708", ORIGINAL_SOURCE_SHA,
         "gh-aw/work-queue/" + ORIGINAL_SOURCE_SHA, "gh-aw-code-worker.lock.yml", 41898282,
         "gh-aw work-queue d_ef8262a3e68600f48828dad443358ce5a9ac11d458fd935b078a1b2a965ac864_1"),
        (PUBLIC, PUBLIC_ID, public_token, "39852724729", RECOVERY1_PUBLIC_SHA, "main", "code-gateway.yml", OWNER_ID,
         "CW issue129 code " + RECOVERY1_WORK_ID),
        (SOURCE, SOURCE_ID, source_token, "39852966443", RECOVERY1_SOURCE_SHA, BRANCH, CONTROLLER, OWNER_ID,
         "CW issue129 launch " + RECOVERY1_WORK_ID),
        (SOURCE, SOURCE_ID, source_token, "39853131813", RECOVERY1_SOURCE_SHA,
         "gh-aw/work-queue/" + RECOVERY1_SOURCE_SHA, "gh-aw-code-worker.lock.yml", 41898282,
         "gh-aw work-queue d_e62d9eeaf7d5fbbedaeb9d5dce8f22542b7a1f805558414125ab90d37e244e59_1"),
        (PUBLIC, PUBLIC_ID, public_token, "39870019362", RECOVERY2_PUBLIC_SHA, "main", "code-gateway.yml", OWNER_ID,
         "CW issue129 code " + RECOVERY2_WORK_ID),
        (SOURCE, SOURCE_ID, source_token, "39870151844", RECOVERY2_SOURCE_SHA, BRANCH, CONTROLLER, OWNER_ID,
         "CW issue129 launch " + RECOVERY2_WORK_ID),
        (SOURCE, SOURCE_ID, source_token, "39870273851", RECOVERY2_SOURCE_SHA,
         "gh-aw/work-queue/" + RECOVERY2_SOURCE_SHA, "gh-aw-code-worker.lock.yml", 41898282,
         "gh-aw work-queue d_1ccd2e9191760f194efbb0dcd269965ba78292b77d234371dd958ab39d823ae0_1"),
    )
    if accelerated:
        marker = call(PUBLIC, "GET", "git/ref/heads/" + MARKER, public_token)
        require(type(marker) is dict and marker.get("ref") == "refs/heads/" + MARKER
                and marker.get("object", {}).get("sha") == RECOVERY3_PUBLIC)
        expected += (
            (PUBLIC, PUBLIC_ID, public_token, "39877788233", RECOVERY3_PUBLIC, "main", "code-gateway.yml", OWNER_ID,
             "CW issue129 code " + RECOVERY_WORK_ID),
            (SOURCE, SOURCE_ID, source_token, "39877875874", RECOVERY3_SOURCE, BRANCH, CONTROLLER, OWNER_ID,
             "CW issue129 launch " + RECOVERY_WORK_ID),
            (SOURCE, SOURCE_ID, source_token, "39877972752", RECOVERY3_SOURCE, "gh-aw/work-queue/" + RECOVERY3_SOURCE,
             "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_3f8f143cf17f300c2f5859459fdfc046958c8037f701e33ca50fb8957aaa0602_1"),
        )
    outcomes = {}
    if successor:
        require(accelerated)
        marker = call(PUBLIC, "GET", "git/ref/heads/" + ACCELERATED_MARKER, public_token)
        require(type(marker) is dict and marker.get("ref") == "refs/heads/" + ACCELERATED_MARKER
                and marker.get("object", {}).get("sha") == ACCELERATED1_PUBLIC)
        expected += (
            (PUBLIC, PUBLIC_ID, public_token, "39883821037", ACCELERATED1_PUBLIC, "main", "code-gateway.yml", OWNER_ID,
             "CW issue129 code " + ACCELERATED_WORK),
            (SOURCE, SOURCE_ID, source_token, "39883932232", ACCELERATED1_SOURCE, BRANCH, CONTROLLER, OWNER_ID,
             "CW issue129 accelerated_launch " + ACCELERATED_WORK),
            (SOURCE, SOURCE_ID, source_token, "39884029905", ACCELERATED1_SOURCE, "gh-aw/work-queue/" + ACCELERATED1_SOURCE,
             "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_28d184129b57493ba0a57d3e81ca083da9b843ca455d90954c0578f935c9184e_1"),
        )
        outcomes = {"39883821037": "cancelled", "39884029905": "cancelled"}
    if third:
        require(successor)
        marker = call(PUBLIC, "GET", "git/ref/heads/" + ACCELERATED2_MARKER, public_token)
        require(type(marker) is dict and marker.get("ref") == "refs/heads/" + ACCELERATED2_MARKER
                and marker.get("object", {}).get("sha") == ACCELERATED2_PUBLIC)
        expected += (
            (PUBLIC, PUBLIC_ID, public_token, "39888458959", ACCELERATED2_PUBLIC, "main", "code-gateway.yml", OWNER_ID,
             "CW issue129 code " + ACCELERATED2_WORK),
            (SOURCE, SOURCE_ID, source_token, "39888573669", ACCELERATED2_SOURCE, BRANCH, CONTROLLER, OWNER_ID,
             "CW issue129 accelerated_launch " + ACCELERATED2_WORK),
            (SOURCE, SOURCE_ID, source_token, "39888673546", ACCELERATED2_SOURCE, "gh-aw/work-queue/" + ACCELERATED2_SOURCE,
             "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_30cce43ff67fc2fbb7a973647eec6879d050ac5f5444473f9c03346cbc6746cd_1"),
        )
        outcomes["39888673546"] = "cancelled"
    if fourth:
        require(third)
        marker = call(PUBLIC, "GET", "git/ref/heads/" + ACCELERATED3_MARKER, public_token)
        require(type(marker) is dict and marker.get("ref") == "refs/heads/" + ACCELERATED3_MARKER
                and marker.get("object", {}).get("sha") == ACCELERATED3_PUBLIC)
        expected += (
            (PUBLIC, PUBLIC_ID, public_token, "39890045831", ACCELERATED3_PUBLIC, "main", "code-gateway.yml", OWNER_ID,
             "CW issue129 code " + ACCELERATED3_WORK),
            (SOURCE, SOURCE_ID, source_token, "39890148979", ACCELERATED3_SOURCE, BRANCH, CONTROLLER, OWNER_ID,
             "CW issue129 accelerated_launch " + ACCELERATED3_WORK),
            (SOURCE, SOURCE_ID, source_token, "39890241163", ACCELERATED3_SOURCE, "gh-aw/work-queue/" + ACCELERATED3_SOURCE,
             "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_173aa0daa460d2af534eb992610379e53cb83c81c413291073c3fff6182a167d_1"),
        )
        outcomes.update({"39890045831": "cancelled", "39890241163": "cancelled"})
    if fifth:
        require(fourth)
        marker = call(PUBLIC, "GET", "git/ref/heads/" + ACCELERATED4_MARKER, public_token)
        require(type(marker) is dict and marker.get("ref") == "refs/heads/" + ACCELERATED4_MARKER
                and marker.get("object", {}).get("sha") == ACCELERATED4_PUBLIC)
        expected += (
            (PUBLIC, PUBLIC_ID, public_token, "39895920569", ACCELERATED4_PUBLIC, "main", "code-gateway.yml", OWNER_ID,
             "CW issue129 code " + ACCELERATED4_WORK),
            (SOURCE, SOURCE_ID, source_token, "39896018022", ACCELERATED4_SOURCE, BRANCH, CONTROLLER, OWNER_ID,
             "CW issue129 accelerated_launch " + ACCELERATED4_WORK),
            (SOURCE, SOURCE_ID, source_token, "39896107117", ACCELERATED4_SOURCE, "gh-aw/work-queue/" + ACCELERATED4_SOURCE,
             "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_a8960252d62ea4ca50e429d9f57cfe14582832fcae40ce1b0e7093146cb408f0_1"),
        )
        outcomes.update({"39895920569": "cancelled", "39896107117": "cancelled"})
    if sixth:
        require(fifth)
        marker = call(PUBLIC, "GET", "git/ref/heads/" + ACCELERATED5_MARKER, public_token)
        require(type(marker) is dict and marker.get("ref") == "refs/heads/" + ACCELERATED5_MARKER
                and marker.get("object", {}).get("sha") == ACCELERATED5_PUBLIC)
        expected += (
            (PUBLIC, PUBLIC_ID, public_token, "39899055795", ACCELERATED5_PUBLIC, "main", "code-gateway.yml", OWNER_ID,
             "CW issue129 code " + ACCELERATED5_WORK),
            (SOURCE, SOURCE_ID, source_token, "39899158430", ACCELERATED5_SOURCE, BRANCH, CONTROLLER, OWNER_ID,
             "CW issue129 accelerated_launch " + ACCELERATED5_WORK),
            (SOURCE, SOURCE_ID, source_token, "39899248735", ACCELERATED5_SOURCE, "gh-aw/work-queue/" + ACCELERATED5_SOURCE,
             "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_86912363fb82d8a127a4883e12632488bf62b5933b2634b305ebb80cbc849a0b_1"),
        )
        outcomes.update({"39899055795": "cancelled", "39899248735": "cancelled"})
    if seventh:
        require(sixth)
        marker = call(PUBLIC, "GET", "git/ref/heads/" + ACCELERATED6_MARKER, public_token)
        require(type(marker) is dict and marker.get("ref") == "refs/heads/" + ACCELERATED6_MARKER
                and marker.get("object", {}).get("sha") == ACCELERATED6_PUBLIC)
        expected += (
            (PUBLIC, PUBLIC_ID, public_token, "39902699407", ACCELERATED6_PUBLIC, "main", "code-gateway.yml", OWNER_ID,
             "CW issue129 code " + ACCELERATED6_WORK),
            (SOURCE, SOURCE_ID, source_token, "39902812771", ACCELERATED6_SOURCE, BRANCH, CONTROLLER, OWNER_ID,
             "CW issue129 accelerated_launch " + ACCELERATED6_WORK),
            (SOURCE, SOURCE_ID, source_token, "39902909796", ACCELERATED6_SOURCE, "gh-aw/work-queue/" + ACCELERATED6_SOURCE,
             "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_90cdffd3f1a48978613a6f8df62c77f416153d0dad48064f0431301bca6ba7b0_1"),
        )
    if eighth:
        require(seventh)
        marker = call(PUBLIC, "GET", "git/ref/heads/" + ACCELERATED7_MARKER, public_token)
        require(type(marker) is dict and marker.get("ref") == "refs/heads/" + ACCELERATED7_MARKER
                and marker.get("object", {}).get("sha") == ACCELERATED7_PUBLIC)
        expected += (
            (PUBLIC, PUBLIC_ID, public_token, "39905633845", ACCELERATED7_PUBLIC, "main", "code-gateway.yml", OWNER_ID,
             "CW issue129 code " + ACCELERATED7_WORK),
            (SOURCE, SOURCE_ID, source_token, "39905741262", ACCELERATED7_SOURCE, BRANCH, CONTROLLER, OWNER_ID,
             "CW issue129 accelerated_launch " + ACCELERATED7_WORK),
            (SOURCE, SOURCE_ID, source_token, "39905830292", ACCELERATED7_SOURCE, "gh-aw/work-queue/" + ACCELERATED7_SOURCE,
             "gh-aw-code-worker.lock.yml", 41898282,
             "gh-aw work-queue d_ffd5219f2a873f02fc17927401c35d0ac64e3b7dee16505b21562ed0c40b5f74_1"),
        )
    for repository, repository_id, token, run_id, sha, branch, workflow, actor, title in expected:
        run = call(repository, "GET", "actions/runs/" + run_id + "/attempts/1", token)
        require(type(run) is dict and str(run.get("id")) == run_id
                and run.get("repository", {}).get("full_name") == repository
                and run.get("repository", {}).get("id") == repository_id
                and run.get("head_sha") == sha and run.get("head_branch") == branch
                and run.get("path") == ".github/workflows/" + workflow
                and run.get("event") == "workflow_dispatch" and run.get("run_attempt") == 1
                and run.get("status") == "completed" and run.get("conclusion") == outcomes.get(run_id, "failure")
                and all(run.get(name, {}).get("id") == actor for name in ("actor", "triggering_actor")))
        if title is not None:
            require(run.get("display_title") == title)


def approval(call, token, own, now):
    run = call(PUBLIC, "GET", "actions/runs/" + own["GITHUB_RUN_ID"], token)
    checked_run(run, repository=PUBLIC, repository_id=PUBLIC_ID, run_id=own["GITHUB_RUN_ID"],
        head=own["GITHUB_SHA"], branch="main", workflow=".github/workflows/code-gateway.yml", now=now)
    require(run.get("display_title") == "CW issue129 code " + own["CW_WORK_ID"])
    branch = call(PUBLIC, "GET", "branches/main", token)
    require(branch.get("protected") is True and branch.get("commit", {}).get("sha") == own["GITHUB_SHA"])
    reviews = call(PUBLIC, "GET", "actions/runs/" + own["GITHUB_RUN_ID"] + "/approvals", token)
    require(type(reviews) is list and len(reviews) == 1)
    review = reviews[0]
    require(review.get("state") == "approved" and review.get("user", {}).get("id") == OWNER_ID
            and type(review.get("environments")) is list and len(review["environments"]) == 1
            and review["environments"][0].get("name") == "paid-one-shot"
            and review["environments"][0].get("can_admins_bypass") is False)
    history = rows(call(PUBLIC, "GET", "actions/workflows/" + WATCHDOG + "/runs?per_page=50", token), "workflow_runs")
    require(any(r.get("head_sha") == own["GITHUB_SHA"] and r.get("event") == "workflow_dispatch"
        and r.get("display_title") == "CW issue88 off_selftest 0" and r.get("status") == "completed"
        and r.get("conclusion") == "success" and r.get("run_attempt") == 1
        and r.get("actor", {}).get("id") == OWNER_ID and 0 <= now - created_at(r) < 3600 for r in history))
    return run


def discover(call, token, repository, workflow, title, sha, branch, started, *, clock, monotonic, pause, owner_required=True, timeout_seconds=75):
    require(type(timeout_seconds) is int and 1 <= timeout_seconds <= 300)
    deadline = monotonic() + timeout_seconds
    while monotonic() < deadline:
        history = rows(call(repository, "GET", "actions/workflows/" + workflow + "/runs?per_page=50", token), "workflow_runs")
        matches = [r for r in history if r.get("display_title") == title and r.get("head_sha") == sha
            and r.get("head_branch") == branch and r.get("event") == "workflow_dispatch"
            and r.get("path") == ".github/workflows/" + workflow and created_at(r) >= started - 2]
        require(len(matches) <= 1)
        if matches:
            run = matches[0]
            require(run.get("run_attempt") == 1 and run.get("status") in LIVE)
            for name in ("actor", "triggering_actor"):
                identity = run.get(name, {})
                require(identity.get("id") == OWNER_ID if owner_required else
                        identity.get("login") == "github-actions[bot]" and identity.get("type") == "Bot")
            if run["status"] == "in_progress":
                return run
        pause(2)
    raise ValueError("CODE_GATEWAY_RUN_NOT_CONFIRMED_NO_REDISPATCH")


def arm_watchdog(call, token, own, *, clock, monotonic, pause):
    started = int(clock())
    call(PUBLIC, "POST", "actions/workflows/" + WATCHDOG + "/dispatches", token,
        {"ref": "main", "inputs": {"mode": "code_watch", "parent_run_id": own["GITHUB_RUN_ID"]}})
    run = discover(call, token, PUBLIC, WATCHDOG, "CW issue88 code_watch " + own["GITHUB_RUN_ID"],
        own["GITHUB_SHA"], "main", started, clock=clock, monotonic=monotonic, pause=pause, owner_required=False)
    deadline = monotonic() + 65
    active_since = None
    while monotonic() < deadline:
        current = call(PUBLIC, "GET", "actions/runs/" + str(run["id"]), token)
        require(current.get("status") == "in_progress" and current.get("run_attempt") == 1
                and current.get("head_sha") == own["GITHUB_SHA"])
        jobs = rows(call(PUBLIC, "GET", "actions/runs/" + str(run["id"]) + "/jobs?per_page=50", token), "jobs")
        active_jobs = [j for j in jobs if j.get("name") == "Independent OFF-only watchdog"]
        require(len(active_jobs) == 1 and active_jobs[0].get("status") == "in_progress")
        steps = active_jobs[0].get("steps", [])
        active = any(s.get("name") == "Verify gate OFF or guard active pilot (no models)"
            and s.get("status") == "in_progress" for s in steps)
        if active:
            if active_since is None:
                active_since = monotonic()
            if monotonic() - active_since >= 25:
                return
        else:
            active_since = None
        pause(5)
    raise ValueError("INDEPENDENT_CODE_OFF_NOT_ARMED")


def execute(environment, *, call=api, clock=time.time, monotonic=time.monotonic, pause=time.sleep):
    own = context(environment)
    eighth = own["CW_WORK_ID"] == ACCELERATED8_WORK
    seventh = own["CW_WORK_ID"] in (ACCELERATED7_WORK, ACCELERATED8_WORK)
    sixth = own["CW_WORK_ID"] in (ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK)
    fifth = own["CW_WORK_ID"] in (ACCELERATED5_WORK, ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK)
    fourth = own["CW_WORK_ID"] in (ACCELERATED4_WORK, ACCELERATED5_WORK, ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK)
    third = own["CW_WORK_ID"] in (ACCELERATED3_WORK, ACCELERATED4_WORK, ACCELERATED5_WORK, ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK)
    successor = own["CW_WORK_ID"] in (ACCELERATED2_WORK, ACCELERATED3_WORK, ACCELERATED4_WORK, ACCELERATED5_WORK, ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK)
    accelerated = own["CW_WORK_ID"] in (ACCELERATED_WORK, ACCELERATED2_WORK, ACCELERATED3_WORK, ACCELERATED4_WORK, ACCELERATED5_WORK, ACCELERATED6_WORK, ACCELERATED7_WORK, ACCELERATED8_WORK)
    marker_name = ACCELERATED8_MARKER if eighth else ACCELERATED7_MARKER if seventh else ACCELERATED6_MARKER if sixth else ACCELERATED5_MARKER if fifth else ACCELERATED4_MARKER if fourth else ACCELERATED3_MARKER if third else ACCELERATED2_MARKER if successor else ACCELERATED_MARKER if accelerated else MARKER
    launch_mode = "accelerated_launch" if accelerated else "launch"
    preflight_only = environment.get("CW_PREFLIGHT_ONLY", "false")
    require(preflight_only in ("true", "false"))
    source_token, public_token = environment["CW_GATEWAY_OPERATOR_TOKEN"], environment["GH_PUBLIC_TOKEN"]
    print("CODE_GATEWAY_VERIFY_APPROVAL", flush=True)
    own_run = approval(call, public_token, own, int(clock()))
    print("CODE_GATEWAY_VERIFY_SOURCE_OFF_AND_RETAINED_BUDGET", flush=True)
    source_preflight(call, source_token, own["CW_SOURCE_SHA"], accelerated=accelerated, continuation=fourth, fifth=fifth, sixth=sixth, seventh=seventh, eighth=eighth)
    print("CODE_GATEWAY_VERIFY_FIXED_TERMINAL_PREDECESSOR", flush=True)
    predecessor(call, source_token, public_token, accelerated=accelerated, successor=successor, third=third, fourth=fourth, fifth=fifth, sixth=sixth, seventh=seventh, eighth=eighth)
    require(call(PUBLIC, "GET", "git/ref/heads/" + marker_name, public_token) is None)
    if preflight_only == "true":
        return "CODE_GATEWAY_PREFLIGHT_VERIFIED_NO_DISPATCH_NO_SPEND"
    # From here any uncertain outcome consumes the attempt. Never repeat a POST.
    try:
        print("CODE_GATEWAY_CONSUME_ONCE_AND_DISPATCH", flush=True)
        call(PUBLIC, "POST", "git/refs", public_token, {"ref": "refs/heads/" + marker_name, "sha": own["GITHUB_SHA"]})
        marker = call(PUBLIC, "GET", "git/ref/heads/" + marker_name, public_token)
        require(marker.get("ref") == "refs/heads/" + marker_name and marker.get("object", {}).get("sha") == own["GITHUB_SHA"])
        started = int(clock())
        call(SOURCE, "POST", "actions/workflows/" + CONTROLLER + "/dispatches", source_token,
            {"ref": BRANCH, "inputs": {"mode": launch_mode, "work_id": own["CW_WORK_ID"],
                "gateway_run_id": own["GITHUB_RUN_ID"], "gateway_sha": own["GITHUB_SHA"]}})
        source = discover(call, source_token, SOURCE, CONTROLLER, "CW issue129 " + launch_mode + " " + own["CW_WORK_ID"],
            own["CW_SOURCE_SHA"], BRANCH, started, clock=clock, monotonic=monotonic, pause=pause)
        issued = int(clock())
        lease = {"version": 1, "package": ACCELERATED_PACKAGE if accelerated else "issue129-20261022", "source_sha": own["CW_SOURCE_SHA"],
            "work_id": own["CW_WORK_ID"], "controller_run_id": str(source["id"]),
            "gateway_run_id": own["GITHUB_RUN_ID"], "gateway_sha": own["GITHUB_SHA"], "issued_at": issued,
            "expires_at": created_at(own_run) + TTL_SECONDS, "cap_cents": 7000 if sixth else 5000 if accelerated else 1000,
            "max_requests": 100 if accelerated else 10}
        public_parent(lease, own_run, now=issued)
        source_parent(lease, source, now=issued, source_sha=own["CW_SOURCE_SHA"], work_id=own["CW_WORK_ID"])
        old = call(SOURCE, "GET", "actions/variables/" + LEASE, source_token)
        value = {"name": LEASE, "value": json.dumps(lease, separators=(",", ":"))}
        call(SOURCE, "POST" if old is None else "PATCH", "actions/variables" if old is None else "actions/variables/" + LEASE,
            source_token, value)
        stored = call(SOURCE, "GET", "actions/variables/" + LEASE, source_token)
        require(stored.get("name") == LEASE and stored.get("value") == value["value"])
        print("CODE_GATEWAY_ARM_INDEPENDENT_OFF", flush=True)
        arm_watchdog(call, public_token, own, clock=clock, monotonic=monotonic, pause=pause)
        for repository, token, run_id in ((PUBLIC, public_token, own["GITHUB_RUN_ID"]), (SOURCE, source_token, str(source["id"]))):
            current = call(repository, "GET", "actions/runs/" + run_id, token)
            if repository == PUBLIC:
                public_parent(lease, current, now=int(clock()))
            else:
                source_parent(lease, current, now=int(clock()), source_sha=own["CW_SOURCE_SHA"], work_id=own["CW_WORK_ID"])
        require(all(read_gate(call, source_token, name) == "false" for name in (PAID, CODE)))
        # CODE first: the existing scheduled guard recognizes the valid code lease
        # before PAID is enabled. Neither flag alone can authorize the worker.
        for name in (CODE, PAID):
            call(SOURCE, "PATCH", "actions/variables/" + name, source_token, {"name": name, "value": "true"})
            require(read_gate(call, source_token, name) == "true")
        print("CODE_GATEWAY_FINITE_CODE_WINDOW_ACTIVE", flush=True)
        deadline = monotonic() + max(0, lease["expires_at"] - int(clock()))
        while monotonic() < deadline:
            current = call(SOURCE, "GET", "actions/runs/" + str(source["id"]), source_token)
            if current.get("status") == "completed":
                require(current.get("conclusion") == "success")
                return "CODE_CONTROLLER_COMPLETED_NATIVE_RESULT_REQUIRES_READBACK"
            source_parent(lease, current, now=int(clock()), source_sha=own["CW_SOURCE_SHA"], work_id=own["CW_WORK_ID"])
            require(all(read_gate(call, source_token, name) == "true" for name in (PAID, CODE)))
            pause(10)
        raise ValueError("CODE_CONTROLLER_TIMEOUT_RESULT_UNVERIFIED")
    finally:
        force_off(call, source_token)


if __name__ == "__main__":
    try:
        print(execute(os.environ))
        print("BOTH_EXECUTION_GATES_OFF_VERIFIED")
    except Exception:
        raise SystemExit("CODE_GATEWAY_DENIED_OR_UNKNOWN_NO_RETRY") from None

