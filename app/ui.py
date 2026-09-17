"""Offline chart configuration: no cloud-share or external service controls."""
import streamlit as st

def offline_chart(figure,**kwargs):
    config=kwargs.pop('config',{})
    config.update(displaylogo=False,modeBarButtonsToRemove=['sendDataToCloud','sendChartToCloud'])
    return st.plotly_chart(figure,config=config,**kwargs)
