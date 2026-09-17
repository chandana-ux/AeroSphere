"""Read-only pre-install navigation checks against the real demo data."""
import os
from pathlib import Path
from streamlit.testing.v1 import AppTest
root=Path(__file__).resolve().parents[1]
app=AppTest.from_file(str(root/'app/dashboard.py'),default_timeout=90).run()
for page in ['HOME','MISSION','FLIGHT','3D WORLD','EVIDENCE','TEMPORAL','INSIGHTS','EXPORT']:
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception,(page,str(app.exception))
    assert not app.error,(page,[e.value for e in app.error])
    print('PASS',page,flush=True)
    if page=='3D WORLD':
        for view in ['GEO','MEASURE','3D']:
            app.get('button_group')[0].set_value(view).run()
            assert not app.exception,(view,str(app.exception))
            assert not app.error,(view,[e.value for e in app.error])
            print('PASS',view,flush=True)
    if page=='EVIDENCE':
        app.slider[0].set_value(1).run()
        assert app.metric[0].value=='0'
        app.slider[0].set_value(77).run()
        assert app.metric[0].value=='29,457'
        app.get('button_group')[0].set_value('QUALITY & COVERAGE').run()
        assert not app.exception,str(app.exception)
        assert not app.error,[e.value for e in app.error]
        print('PASS coverage and replay boundaries',flush=True)
