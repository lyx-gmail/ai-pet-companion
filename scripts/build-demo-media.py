"""Export real-device footage. Source JSON stays private; originals are read only."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path, required=True)
    args = parser.parse_args()
    sources = {item['id']: Path(item['path']).resolve() for item in json.loads(args.sources.read_text(encoding='utf-8'))}
    assert all(p.is_file() for p in sources.values()), 'Missing source footage'
    root = Path(__file__).resolve().parents[1]
    media = root/'docs/media'
    work = root/'.runtime/media-review/export'
    media.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    ffmpeg = str(args.ffmpeg.resolve())

    def run(*options):
        result = subprocess.run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', *map(str, options)], capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.decode('utf-8', errors='replace')[-2500:])

    # HLG phone footage needs an actual SDR conversion before GIF / H.264 export.
    tone = 'zscale=t=linear:npl=100,format=gbrpf32le,tonemap=tonemap=hable:desat=0,zscale=p=bt709:t=bt709:m=bt709:r=limited,format=yuv420p'
    font = "fontfile='C\\:/Windows/Fonts/msyh.ttc'"
    label = lambda text, size, y: f"drawtext={font}:text='{text}':fontsize={size}:fontcolor=white:x=40:y={y}"
    run('-ss', 3, '-i', sources[1], '-vf',
        f'crop=2880:1620:480:0,scale=1280:720,{tone},pad=1280:900:0:100:color=0x10191f,'+
        label('AI Pet Companion', 42, 25)+','+label('全屏表情 · 实体养成 · AI 语音 · 个人记忆', 27, 841),
        '-frames:v', 1, media/'cover.jpg')

    for source, start, duration, name in [(1, 1, 7, 'expressions'), (2, 0, 15.8, 'care'), (3, 0, 17.3, 'sleep')]:
        run('-ss', start, '-t', duration, '-i', sources[source], '-filter_complex',
            f'[0:v]fps=8,crop=2880:2160:480:0,scale=400:300,{tone},split[a][b];'
            '[a]palettegen=max_colors=64:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle',
            '-an', '-loop', 0, media/f'{name}.gif')
        print(f'GIF {name}', flush=True)

    # Continuous source ranges: do not shorten an AI wait into an apparent fast response.
    # Source 4 is the superseded satiety take; source 7 is the replacement.
    chapters = [(1, 0.5, 6, '全屏动态表情'), (2, 0, 15.8, '按键喂食与抚摸'),
                (3, 0, 17.3, '睡眠与唤醒'), (7, 0, 16.43, 'AI 语音查询真实状态'),
                (5, 12, 31.43, '记住称呼与喜好 · 按键确认'), (6, 0, 26.25, '更正喜好 · 再次确认')]
    timeline = []
    elapsed = 0
    for index, (source, start, duration, title) in enumerate(chapters, 1):
        part = work/f'part-{index}.mp4'
        run('-ss', start, '-t', duration, '-i', sources[source], '-vf',
            f'scale=1280:720,{tone},pad=1280:800:0:80:color=0x10191f,'+label(f'0{index} / {title}', 29, 22),
            '-r', 30, '-c:v', 'libx264', '-preset', 'fast', '-crf', 23, '-pix_fmt', 'yuv420p',
            '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709',
            '-c:a', 'aac', '-b:a', '128k', '-ar', 48000, '-ac', 2, '-movflags', '+faststart', part)
        timeline.append(dict(chapter=index, title=title, source=sources[source].name,
                             source_start_seconds=start, source_duration_seconds=duration,
                             demo_start_seconds=round(elapsed, 2)))
        elapsed += duration
        print(f'VIDEO {index}: {title.encode("ascii", errors="backslashreplace").decode()}', flush=True)
    (work/'concat.txt').write_text(''.join(f"file 'part-{i}.mp4'\n" for i in range(1, len(chapters)+1)), encoding='utf-8')
    run('-f', 'concat', '-safe', 0, '-i', work/'concat.txt', '-c', 'copy', '-movflags', '+faststart', work/'ai-pet-demo.mp4')
    (media/'chapters.json').write_text(json.dumps(dict(speed=1, audio='original recording',
        footage='separate recorded takes', chapters=timeline), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    outputs = [media/'cover.jpg', *media.glob('*.gif'), work/'ai-pet-demo.mp4']
    assert all(p.stat().st_size > 1000 for p in outputs)
    print(json.dumps({p.name: round(p.stat().st_size/1024/1024, 2) for p in outputs}))


if __name__ == '__main__':
    main()
