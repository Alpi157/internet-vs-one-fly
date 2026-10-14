from dataclasses import replace
import pytest
from flybench.encoding_v2 import HandStrikeV2,encode_hand_v2,standard_feature_peaks


def encode(strike):
    return encode_hand_v2(strike,fly_x=0.,fly_y=0.,heading_x=1.,heading_y=0.,hand_radius=.75,initial_height=8.,dt_ms=.5,input_gain=4.)


def test_population_mapping_by_field_name():
    e=encode(HandStrikeV2(True,0.,0.,120.,.05))
    assert e.lc4_left_drive+e.lc4_right_drive==pytest.approx(e.expansion_feature*4)
    assert e.lplc2_left_drive+e.lplc2_right_drive==pytest.approx(e.size_feature*4)
    assert e.expansion_feature!=e.size_feature


def test_mirror_far_and_matched_size_speed():
    strike=HandStrikeV2(True,0.,1.5,100.,.05)
    left,right=encode(strike),encode(replace(strike,aim_y=-1.5))
    assert left.lc4_left_drive==pytest.approx(right.lc4_right_drive)
    assert left.lplc2_left_drive==pytest.approx(right.lplc2_right_drive)
    far=encode(replace(strike,aim_y=20.))
    assert sum((far.lc4_left_drive,far.lc4_right_drive))<sum((left.lc4_left_drive,left.lc4_right_drive))
    slow=encode(HandStrikeV2(True,0.,0.,100.,.05))
    fast=encode(HandStrikeV2(True,0.,0.,50.,.1))
    assert slow.angular_radius==fast.angular_radius
    assert slow.lc4_left_drive<fast.lc4_left_drive


@pytest.mark.parametrize('strike',[HandStrikeV2(False),HandStrikeV2(True,0,0,160.5,.05),HandStrikeV2(True,0,0,0,0)])
def test_no_static_or_post_impact_drive(strike):
    e=encode(strike)
    assert e.lc4_left_drive==e.lc4_right_drive==e.lplc2_left_drive==e.lplc2_right_drive==0.
