"""Replay held-out clips through the real temporal state machine without the UI."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import torch
from vinfall.config import DATA, DEMO_SEQUENCES, ROOT
from vinfall.model import TemporalClassifier
from vinfall.pose import PoseExtractor
from vinfall.tracking import PeopleMonitor
from train_model import TEST_ADLS


def main():
    torch.set_num_threads(4)
    classifier, extractor = TemporalClassifier(), PoseExtractor()
    report = {'positive_pairs': [], 'negative_clips': []}
    for sequence in [*DEMO_SEQUENCES, *sorted(TEST_ADLS)]:
        cameras=[]
        for video in sorted(DATA.glob(sequence+'-cam*.mp4')):
            data = extractor.extract_people(video)
            monitor = PeopleMonitor(classifier)
            alerts, occlusions, observations = [], [], []
            for i,t in enumerate(data['times']):
                start, stop = data['offsets'][i:i+2]
                detections = [{'points':data['points'][j], 'box':data['boxes'][j],
                               'appearance':data['appearances'][j]} for j in range(start,stop)]
                for event in monitor.update(float(t),detections,float(data['aspect'])):
                    (alerts if event['kind']=='fall' else occlusions).append(round(float(t),2))
                    observations.append(event)
            cameras.append({'file':video.name,'alert_times':alerts,'occlusion_times':occlusions,
                            'observations':observations,'tracks_created':monitor.next_id-1})
        record={'sequence':sequence,'cameras':cameras,'alert':any(c['alert_times'] or c['occlusion_times'] for c in cameras)}
        report['positive_pairs' if sequence in DEMO_SEQUENCES else 'negative_clips'].append(record)
        print(json.dumps(record),flush=True)
    report['summary']={'fall_pairs_detected':sum(x['alert'] for x in report['positive_pairs']),
                       'fall_pairs_total':len(report['positive_pairs']),
                       'normal_clips_false_alerts':sum(x['alert'] for x in report['negative_clips']),
                       'normal_clips_total':len(report['negative_clips'])}
    report['limits']='Development replay with per-person tracking of 5 demo pairs and 5 normal clips. These clips were excluded from LSTM training, but temporal confirmation rules were refined using these replays; this is NOT an independent end-to-end test or subject-independent/clinical validation. URFD has mostly one person; this report does not validate crowded scenes or occluded falls. Occlusion times are heuristic alerts, not observed falls.'
    target=ROOT/'docs'/'demo_evaluation.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(report['summary'],flush=True)


if __name__=='__main__':
    main()
