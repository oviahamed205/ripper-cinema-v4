"""Evidence-based bounded-sample checks; never a whole-file playback guarantee."""
from __future__ import annotations
import asyncio
from pathlib import Path
import re
import shutil
import tempfile
import json
from urllib.parse import urljoin
from .models import Probe
from .transport import Transport, FetchError


def signature(data: bytes) -> str | None:
    if len(data)>=12 and data[4:8]==b"ftyp": return "mp4"
    if data.startswith(bytes.fromhex("1a45dfa3")): return "ebml"
    if len(data)>=12 and data[:4]==b"RIFF" and data[8:12]==b"AVI ": return "avi"
    if len(data)>=377 and all(data[i]==0x47 for i in (0,188,376)): return "mpegts"
    return None


def valid_range(headers: dict, start: int, body_length: int) -> bool:
    match=re.fullmatch(r"bytes (\d+)-(\d+)/(\d+|\*)",headers.get("content-range", ""),re.I)
    if not match: return False
    a,b=int(match[1]),int(match[2])
    return a==start and b>=a and b-a+1==body_length and (match[3]=="*" or int(match[3])>b)


class Verifier:
    def __init__(self, transport: Transport, *, executable: str | None = None):
        self.http=transport; self.config=transport.config
        self.slots=asyncio.Semaphore(self.config.probe_concurrency)
        self.executable=executable or shutil.which("ffprobe")
        if not self.executable:
            raise RuntimeError("ffprobe is required; install FFmpeg and add it to PATH")

    async def probe(self,url: str) -> Probe:
        try:
            response=await self.http.fetch(url,max_bytes=self.config.max_media_bytes,
                headers={"Range":f"bytes=0-{self.config.max_media_bytes-1}"})
            if response.status not in {200,206}:
                return Probe("unreachable",f"http_{response.status}")
            data=response.body
            if data.lstrip().startswith(b"#EXTM3U"):
                return await self._hls(response.url,data)
            if data.lstrip().lower().startswith((b"<html",b"<!doctype",b"<script")):
                return Probe("invalid","html_not_video",bytes_sampled=len(data))
            kind=signature(data)
            if not kind:
                return Probe("invalid","unrecognized_video_container",bytes_sampled=len(data))
            result=await self._ffprobe(data,kind)
            if result.verified and self.config.check_resume:
                result.resume_supported=await self._resume(response.url)
            return result
        except FetchError as exc:
            return Probe("unreachable",str(exc))

    async def _resume(self,url):
        try:
            r=await self.http.fetch(url,max_bytes=1,headers={"Range":"bytes=5000-5000"})
            return r.status==206 and valid_range(r.headers,5000,len(r.body))
        except FetchError:
            return None

    async def _hls(self,url: str,body: bytes) -> Probe:
        seen=set()
        for _ in range(self.config.playlist_depth):
            if url in seen: return Probe("invalid","playlist_loop")
            seen.add(url)
            if len(body)>self.config.max_playlist_bytes:
                return Probe("unsupported","playlist_size_limit")
            lines=[x.strip() for x in body.decode("utf-8",errors="replace").splitlines() if x.strip()]
            if not lines or lines[0]!="#EXTM3U": return Probe("invalid","invalid_playlist")
            # Encryption is deliberately not bypassed or misreported as verified.
            for line in lines:
                if line.startswith("#EXT-X-KEY:") and not re.search(r"METHOD=NONE(?:,|$)",line):
                    return Probe("unsupported","encrypted_hls_not_supported")
            variants=[]
            for i,line in enumerate(lines):
                if line.startswith("#EXT-X-STREAM-INF:"):
                    following=next((x for x in lines[i+1:] if not x.startswith("#")),None)
                    if following: variants.append(following)
            if variants:
                # Select first advertised variant, not a fabricated quality label.
                r=await self.http.fetch(urljoin(url,variants[0]),max_bytes=self.config.max_playlist_bytes+1)
                if r.status not in {200,206}: return Probe("unreachable",f"playlist_http_{r.status}")
                url,body=r.url,r.body
                continue
            segments=[x for x in lines if not x.startswith("#")]
            if not segments: return Probe("incomplete","playlist_has_no_segments")
            init=None
            for line in lines:
                if line.startswith("#EXT-X-MAP:"):
                    found=re.search(r'URI="([^"]+)"',line)
                    if found: init=found[1]
                    break
            if any(line.startswith("#EXT-X-BYTERANGE:") or (line.startswith("#EXT-X-MAP:") and "BYTERANGE=" in line) for line in lines):
                return Probe("unsupported","hls_byteranges_not_supported")
            sample=bytearray()
            resources=([init] if init else [])+[segments[0]]
            for resource in resources:
                remaining=self.config.max_media_bytes-len(sample)
                if remaining<64: return Probe("incomplete","sample_budget_exhausted",bytes_sampled=len(sample))
                # urljoin keeps the URI's complete query string, including signatures.
                r=await self.http.fetch(urljoin(url,resource),max_bytes=remaining,
                    headers={"Range":f"bytes=0-{remaining-1}"})
                if r.status not in {200,206}: return Probe("unreachable",f"segment_http_{r.status}",bytes_sampled=len(sample))
                sample.extend(r.body)
            kind=signature(sample)
            if not kind: return Probe("invalid","invalid_hls_media_signature",bytes_sampled=len(sample))
            result=await self._ffprobe(bytes(sample),kind)
            if result.verified: result.container="hls/"+str(result.container)
            return result
        return Probe("unsupported","playlist_depth_limit")

    async def _ffprobe(self,data: bytes,kind: str) -> Probe:
        async with self.slots:
            return await self._run_ffprobe(data,kind)

    async def _run_ffprobe(self,data: bytes,kind: str) -> Probe:
        path=None; proc=None
        try:
            with tempfile.NamedTemporaryFile(prefix="omega-probe-",suffix=".bin",delete=False) as f:
                path=Path(f.name)
            write=asyncio.create_task(asyncio.to_thread(path.write_bytes,data))
            try:await asyncio.shield(write)
            except asyncio.CancelledError:
                await write
                raise
            proc=await asyncio.create_subprocess_exec(self.executable,
                "-v","error","-protocol_whitelist","file,pipe",
                "-probesize",str(self.config.max_media_bytes),"-analyzeduration","2000000",
                "-show_entries","stream=codec_type,codec_name,width,height:format=format_name,bit_rate",
                "-of","json",str(path),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
            try:
                stdout,_=await asyncio.wait_for(proc.communicate(),timeout=self.config.probe_timeout)
            except (TimeoutError,asyncio.CancelledError):
                if proc.returncode is None: proc.kill()
                await proc.wait()
                raise
            if proc.returncode!=0:
                return Probe("incomplete","ffprobe_could_not_parse_sample",container=kind,bytes_sampled=len(data))
            payload=json.loads(stdout)
            streams=payload.get("streams",[])
            video=next((s for s in streams if s.get("codec_type")=="video"),None)
            audio=next((s for s in streams if s.get("codec_type")=="audio"),None)
            if not video or video.get("codec_name") in {None,"","unknown"} or not video.get("width") or not video.get("height"):
                return Probe("incomplete","no_identified_video_stream",container=kind,bytes_sampled=len(data))
            fmt=payload.get("format",{})
            bitrate=fmt.get("bit_rate")
            return Probe("verified","video_identified_in_bounded_sample",
                container=fmt.get("format_name") or kind,video_codec=video["codec_name"],
                audio_codec=audio.get("codec_name") if audio else None,
                width=int(video["width"]),height=int(video["height"]),
                sample_bitrate_bps=int(bitrate) if str(bitrate).isdigit() else None,bytes_sampled=len(data))
        except TimeoutError:
            return Probe("incomplete","ffprobe_timeout",container=kind,bytes_sampled=len(data))
        except (OSError,ValueError,TypeError):
            return Probe("incomplete","ffprobe_unavailable_or_invalid_output",container=kind,bytes_sampled=len(data))
        finally:
            if proc is not None and proc.returncode is None:
                proc.kill(); await proc.wait()
            if path is not None: path.unlink(missing_ok=True)
