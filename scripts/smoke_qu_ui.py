"""Exercise Qu recognition, dictionary search and numbered GUI paths together."""
import json,time,tkinter as tk
from pathlib import Path
import cv2
from wordlink.paths import FIXTURES_DIR, ROOT
from wordlink.vision.tiles import detect_tiles
from wordlink.ui.app import create_app


def main():
    original=cv2.imread(str(FIXTURES_DIR/'boards/frame_010.000.png'))
    x,y,w,h=detect_tiles(original)[0]
    qu=cv2.imread(str(FIXTURES_DIR/'tiles/qu-arial.png'))
    original[y:y+h,x:x+w]=cv2.resize(qu,(w,h))
    path=ROOT/'artifacts/qu_gui_input.png'
    cv2.imwrite(str(path),original)
    root=tk.Tk(); errors=[]
    root.report_callback_exception=lambda kind,value,trace: errors.append(str(value))
    app=create_app(root,image_path=path)
    try:
        limit=time.monotonic()+30
        while (app.board is None or app.busy) and time.monotonic()<limit:
            root.update();time.sleep(.01)
        assert app.board is not None and app.board.letters[0]=='QU'
        assert not app._recognition.warnings,app._recognition.warnings
        assert app.letter_vars[0].get()=='QU'
        index=next(i for i,r in enumerate(app.ranked_words) if r.found.word=='QUERN' and r.found.path==(0,5,6,7))
        app.select_candidate(index);root.update()
        assert app.best_word_var.get()=='QUERN'
        assert app.path_var.get()=='Path: 1 → 6 → 7 → 8'
        assert app.canvas.find_withtag('path')
        for row in app.ranked_words:
            found=row.found
            assert ''.join(app.board.letters[i] for i in found.path)==found.word
            assert len(found.path)==len(set(found.path))
            assert sum(app.board.dots[i] for i in found.path)==found.dot_sum
        assert not errors,errors
        report={'passed':True,'scope':'Actual Tk synthetic Qu replacement in independently labeled board crop','recognized_token':app.board.letters[0],'word':app.best_word_var.get(),'path':[1,6,7,8],'warnings':list(app._recognition.warnings),'callback_errors':errors,'all_candidate_paths_checked':len(app.ranked_words)}
        (ROOT/'artifacts/qu_gui_smoke.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report),flush=True)
    finally:app.close()

if __name__=='__main__':main()
