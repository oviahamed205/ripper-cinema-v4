"""One post's lifecycle; candidate attempts race under explicit limits."""
from __future__ import annotations
import asyncio
import time
from .models import PostResult
from .discovery import harvest_candidates
from .transport import FetchError
from .resolvers import ResolveError


class Pipeline:
    def __init__(self,http,resolver,verifier,storage):
        self.http=http;self.resolver=resolver;self.verifier=verifier;self.storage=storage;self.config=http.config

    async def process(self,result: PostResult):
        start=time.perf_counter()
        tasks=[]
        try:
            async with asyncio.timeout(self.config.post_timeout):
                if result.post.selection_basis=="direct_input":
                    candidates=[result.post.url]
                else:
                    t=time.perf_counter()
                    page=await self.http.fetch(result.post.url,max_bytes=self.config.max_html_bytes)
                    result.timings_ms["post_fetch"] = round((time.perf_counter()-t)*1000,2)
                    if page.status!=200:
                        result.status="unreachable";result.reason=f"post_http_{page.status}";return
                    t=time.perf_counter()
                    candidates=harvest_candidates(page.text,page.url,self.config.candidate_limit)
                    result.timings_ms["candidate_discovery"] = round((time.perf_counter()-t)*1000,2)
                if not candidates:
                    result.status="unsupported";result.reason="no_candidate_links";return
                slots=asyncio.Semaphore(self.config.candidate_concurrency)
                async def attempt(url):
                    async with slots:
                        result.candidate_checks+=1
                        t=time.perf_counter()
                        final=await self.storage.cache_get(url) if self.config.cache_seconds else None
                        cached=bool(final)
                        if final:
                            result.cache_hits+=1
                        else:
                            final=await self.resolver.resolve(url)
                        resolve_ms=(time.perf_counter()-t)*1000
                        t=time.perf_counter()
                        probe=await self.verifier.probe(final)
                        if cached and not probe.verified:
                            await self.storage.cache_delete(url)
                            final=await self.resolver.resolve(url)
                            probe=await self.verifier.probe(final)
                        probe_ms=(time.perf_counter()-t)*1000
                        if probe.verified:
                            await self.storage.cache_put(url,final,self.config.cache_seconds)
                        else:
                            await self.storage.cache_delete(url)
                        return final,probe,resolve_ms,probe_ms
                tasks=[asyncio.create_task(attempt(url)) for url in dict.fromkeys(candidates)]
                best=None; failures=[]
                for future in asyncio.as_completed(tasks):
                    try:
                        item=await future
                        if best is None or item[1].status=="incomplete":best=item
                        if item[1].verified:
                            best=item;break
                    except (ResolveError,FetchError) as exc:
                        failures.append(str(exc))
                    except Exception:
                        failures.append("candidate_exception")
                if best:
                    result.final_url,result.probe,resolve_ms,probe_ms=best
                    result.status=result.probe.status;result.reason=result.probe.reason
                    result.timings_ms["selected_candidate_resolution"]=round(resolve_ms,2)
                    result.timings_ms["selected_candidate_validation_including_refresh"]=round(probe_ms,2)
                else:
                    result.status="failed";result.reason=failures[-1] if failures else "no_candidate_completed"
        except TimeoutError:
            result.status="timed_out";result.reason="post_deadline"
        except FetchError as exc:
            result.status="unreachable";result.reason=str(exc)
        finally:
            for task in tasks:
                if not task.done():task.cancel()
            if tasks:await asyncio.gather(*tasks,return_exceptions=True)
            result.total_ms=round((time.perf_counter()-start)*1000,2)
