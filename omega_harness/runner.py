"""Actual site/post fan-out, first-result cancellation and progressive snapshots."""
from __future__ import annotations
import asyncio
from collections import Counter
import time
import uuid
from .config import Config
from .models import Post,PostResult,safe_url,utc_now
from .discovery import discover_posts
from .transport import Transport,FetchError
from .verification import Verifier
from .storage import Storage
from .resolvers import BasicResolver,RipperResolver
from .pipeline import Pipeline


class Harness:
    def __init__(self,config: Config,*,transport=None,resolver=None,verifier=None,on_event=None):
        self.config=config
        self.http=transport or Transport(config)
        self.resolver=resolver or (RipperResolver(self.http) if config.resolver=="ripper" else BasicResolver(self.http))
        self.verifier=verifier or Verifier(self.http)
        self.storage=Storage(config.output_dir)
        self.pipeline=Pipeline(self.http,self.resolver,self.verifier,self.storage)
        self.on_event=on_event
        self.posts: dict[str,PostResult]={}
        self.sites: list[dict]=[]
        self.run_id=uuid.uuid4().hex
        self.stop=asyncio.Event()
        self.post_slots=asyncio.Semaphore(config.post_concurrency)
        self.site_slots=asyncio.Semaphore(config.site_concurrency)
        self.started=0.0;self.first_result_ms=None;self.reason="running"
        self.snapshot_lock=asyncio.Lock()
        self._used=False

    def _event(self,kind,**data):
        if self.on_event:self.on_event({"event":kind,**data})

    def payload(self):
        counts=Counter(p.status for p in self.posts.values())
        return {
            "schema_version":1,"run_id":self.run_id,"timestamp":utc_now(),
            "mode":self.config.mode,"resolver":self.config.resolver,"completion_reason":self.reason,
            "elapsed_ms":round((time.perf_counter()-self.started)*1000,2),
            "time_to_first_verified_ms":self.first_result_ms,
            "summary":{"sites_requested":len(self.sites),"posts_discovered":len(self.posts),
                       "post_status_counts":dict(counts)},
            "limits":{"run_deadline_seconds":self.config.run_timeout,
                      "post_deadline_seconds":self.config.post_timeout,
                      "requests":self.config.request_concurrency,"per_destination_host":self.config.per_host_concurrency,
                      "active_posts":self.config.post_concurrency,"candidates_per_post":self.config.candidate_concurrency,
                      "sample_bytes_per_probe":self.config.max_media_bytes,"ffprobe_processes":self.config.probe_concurrency},
            "network":dict(self.http.stats),
            "verification_scope":"Video metadata identified in bounded sample; not full-file playback or title identity verification.",
            "sites":self.sites,"posts":[p.public() for p in self.posts.values()]}

    async def _snapshot(self):
        async with self.snapshot_lock:
            private=[{"post_url":r.post.url,"stream_url":r.final_url,"probe":r.probe.__dict__}
                for r in self.posts.values() if r.status=="verified" and r.probe]
            await self.storage.snapshot(self.payload(),private)

    def _register(self,post):
        if post.url in self.posts:return None
        result=PostResult(post)
        self.posts[post.url]=result
        return result

    async def _post(self,result):
        try:
            async with self.post_slots:
                result.status="running"
                begin=asyncio.create_task(self.storage.begin(self.run_id,result.post.url))
                try:
                    result.attempts=await asyncio.shield(begin)
                except asyncio.CancelledError:
                    result.attempts=await begin
                    raise
                self._event("post_started",url=safe_url(result.post.url))
                await self.pipeline.process(result)
                if result.status=="verified":
                    if self.first_result_ms is None:
                        self.first_result_ms=round((time.perf_counter()-self.started)*1000,2)
                    # Signal immediately; remaining work is cancelled by run().
                    if self.config.mode=="first":self.stop.set()
        except asyncio.CancelledError:
            if result.status not in {"verified","invalid","incomplete","unsupported","unreachable","failed","timed_out"}:
                result.status="cancelled";result.reason="run_stopped_before_completion"
            raise
        except Exception:
            result.status="failed";result.reason="post_pipeline_exception"
        finally:
            if result.attempts:
                await self.storage.finish(self.run_id,result)
            self._event("post_finished",url=safe_url(result.post.url),status=result.status)
            await self._snapshot()

    async def _site(self,url,record):
        try:
            async with self.site_slots:
                record["status"]="discovering"
                response=await self.http.fetch(url,max_bytes=self.config.max_html_bytes)
                record["fetch_ms"]=response.elapsed_ms
                if response.status!=200:
                    record["status"]="unreachable";record["reason"]=f"index_http_{response.status}";return
                posts=discover_posts(response.text,response.url,self.config.post_limit)
                record["discovered_posts"]=len(posts)
                record["status"]="processing" if posts else "no_posts"
            # Release discovery permits before processing posts.
            async with asyncio.TaskGroup() as group:
                for post in posts:
                    result=self._register(post)
                    if result is not None:group.create_task(self._post(result))
            if posts:record["status"]="complete"
        except asyncio.CancelledError:
            record["status"]="cancelled";record["reason"]="run_stopped_before_completion";raise
        except FetchError as exc:
            record["status"]="unreachable";record["reason"]=str(exc)
        except Exception:
            record["status"]="failed";record["reason"]="site_pipeline_exception"
        finally:
            self._event("site_finished",url=safe_url(url),status=record["status"])
            await self._snapshot()

    async def run(self,*,sites=(),urls=()):
        if self._used:raise RuntimeError("Use a new Harness instance for each run")
        self._used=True
        sites=list(dict.fromkeys(sites));urls=list(dict.fromkeys(urls))
        if not sites and not urls:raise ValueError("Supply at least one site or media/gateway URL")
        await self.storage.open()
        self.started=time.perf_counter()
        for site in sites:self.sites.append({"url":safe_url(site),"status":"pending","discovered_posts":0})
        async def work():
            async with asyncio.TaskGroup() as group:
                for site,record in zip(sites,self.sites):group.create_task(self._site(site,record))
                for url in urls:
                    result=self._register(Post(url,"Provided media or gateway URL",selection_basis="direct_input"))
                    if result is not None:group.create_task(self._post(result))
        jobs=asyncio.create_task(work())
        first=asyncio.create_task(self.stop.wait())
        try:
            await self._snapshot()
            done,_=await asyncio.wait({jobs,first},timeout=self.config.run_timeout,return_when=asyncio.FIRST_COMPLETED)
            if jobs in done:
                await jobs
                self.reason="completed"
            elif first in done:
                self.reason="first_verified"
            else:
                self.reason="run_deadline"
        except asyncio.CancelledError:
            self.reason="interrupted";raise
        except Exception:
            self.reason="run_error"
        finally:
            for task in (jobs,first):
                if not task.done():task.cancel()
            await asyncio.gather(jobs,first,return_exceptions=True)
            try:
                await self._snapshot()
            finally:
                await self.http.close()
                await self.storage.close()
        self._event("run_finished",reason=self.reason,verified=sum(r.status=="verified" for r in self.posts.values()))
        return self.payload()
