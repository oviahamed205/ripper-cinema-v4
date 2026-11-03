from __future__ import annotations
import argparse
import asyncio
import importlib.util
import shutil
import sys
from pathlib import Path
from . import __version__
from .config import Config
from .runner import Harness


def parser():
    p=argparse.ArgumentParser(description="Bounded, evidence-based media verification harness")
    p.add_argument("--version",action="version",version=__version__)
    sub=p.add_subparsers(dest="command",required=True)
    sub.add_parser("doctor",help="Check local runtime dependencies without network access")
    r=sub.add_parser("run",help="Discover, resolve and verify within an explicit budget")
    r.add_argument("--site",action="append",default=[],help="Site homepage URL; repeatable")
    r.add_argument("--sites-file",type=Path,help="One authorized homepage URL per line")
    r.add_argument("--url",action="append",default=[],help="Media or gateway URL; repeatable")
    r.add_argument("--mode",choices=["first","audit"],default="first")
    r.add_argument("--resolver",choices=["basic","ripper"],default="basic")
    r.add_argument("--limit",type=int,default=5,help="Posts per site")
    r.add_argument("--deadline",type=float,help="Network-work budget, seconds; default 10 first / 60 audit")
    r.add_argument("--post-timeout",type=float,default=12)
    r.add_argument("--request-timeout",type=float,default=6)
    r.add_argument("--probe-timeout",type=float,default=3)
    r.add_argument("--probes",type=int,default=2,help="Concurrent ffprobe subprocesses")
    r.add_argument("--requests",type=int,default=8,help="Global HTTP concurrency")
    r.add_argument("--per-host",type=int,default=2)
    r.add_argument("--posts",type=int,default=6,help="Concurrent post pipelines")
    r.add_argument("--sites",type=int,default=4,help="Concurrent homepage discovery")
    r.add_argument("--candidates",type=int,default=2,help="Concurrent candidates per post")
    r.add_argument("--candidate-limit",type=int,default=6)
    r.add_argument("--sample-bytes",type=int,default=2097152)
    r.add_argument("--check-resume",action="store_true",help="Extra range request after successful verification")
    r.add_argument("--no-cache",action="store_true",help="Disable use and storage of resolution cache")
    r.add_argument("--allow-private-network",action="store_true",help="Permit local/private targets (trusted testing only)")
    r.add_argument("--output",default="omega-output",help="Private output DIRECTORY, not a JSON filename")
    r.add_argument("--quiet",action="store_true")
    return p


def doctor():
    checks={"Python >= 3.11":sys.version_info>=(3,11),"ffprobe on PATH":bool(shutil.which("ffprobe")),
            "HTTPX installed":importlib.util.find_spec("httpx") is not None,
            "BeautifulSoup installed":importlib.util.find_spec("bs4") is not None}
    for name,ok in checks.items():print(f"{'OK' if ok else 'MISSING'}  {name}")
    print("Optional Ripper adapter: install your original Ripper project separately.")
    print("No network requests performed.")
    return 0 if all(checks.values()) else 2


async def async_main(argv=None):
    args_list=list(sys.argv[1:] if argv is None else argv)
    # Compatibility launcher accepts flags without an explicit 'run' subcommand.
    if args_list and args_list[0].startswith("--") and args_list[0] not in {"--help","--version"}:
        args_list.insert(0,"run")
    p=parser();a=p.parse_args(args_list)
    if a.command=="doctor":return doctor()
    sites=a.site
    if a.sites_file:
        try:sites += [line.strip() for line in a.sites_file.read_text().splitlines() if line.strip() and not line.lstrip().startswith("#")]
        except OSError:p.error("Could not read sites file")
    if not sites and not a.url:p.error("run requires --site, --sites-file or --url")
    try:
        config=Config(mode=a.mode,resolver=a.resolver,post_limit=a.limit,
            run_timeout=a.deadline if a.deadline is not None else (10 if a.mode=="first" else 60),
            post_timeout=a.post_timeout,request_timeout=a.request_timeout,probe_timeout=a.probe_timeout,probe_concurrency=a.probes,
            request_concurrency=a.requests,per_host_concurrency=a.per_host,post_concurrency=a.posts,
            site_concurrency=a.sites,candidate_concurrency=a.candidates,candidate_limit=a.candidate_limit,
            max_media_bytes=a.sample_bytes,check_resume=a.check_resume,cache_seconds=0 if a.no_cache else 60,
            allow_private_network=a.allow_private_network,output_dir=a.output)
    except ValueError as exc:p.error(str(exc))
    def event(e):
        if a.quiet:return
        if e["event"]=="post_finished":print(f"Post {e['status']}: {e['url']}",flush=True)
        elif e["event"]=="site_finished":print(f"Site {e['status']}: {e['url']}",flush=True)
    try:
        h=Harness(config,on_event=event)
        payload=await h.run(sites=sites,urls=a.url)
    except RuntimeError as exc:
        print(str(exc),file=sys.stderr);return 2
    except OSError:
        print("Local storage or process error; check output permissions and ffprobe installation.",file=sys.stderr);return 2
    counts=payload["summary"]["post_status_counts"]
    if not a.quiet:
        print(f"Finished: {payload['completion_reason']}; verified samples: {counts.get('verified',0)}")
        print("results.json is redacted. Playback URLs are in streams.private.json; do not share that file.")
        print("Deadlines stop network work; cancellation and durable file cleanup can add a small delay.")
    if payload["completion_reason"] in {"run_deadline","interrupted","run_error"}:return 3
    return 0 if counts.get("verified",0) else 1


def main(argv=None):
    try:return asyncio.run(async_main(argv))
    except KeyboardInterrupt:return 130
