import pytest
from skill_observatory.store import Store
from skill_observatory.packages import freeze_package,read_package,changed_files,snapshot_package


def test_full_package_identity_changes_on_any_file_and_exact_surface(tmp_path):
    s=Store(tmp_path/'state')
    a=freeze_package(s,{'SKILL.md':b'guide','refs/flow.md':b'old'})
    b=freeze_package(s,{'SKILL.md':b'guide','refs/flow.md':b'new'})
    assert read_package(s,a)['refs/flow.md']==b'old'
    assert a['package_digest']!=b['package_digest']
    assert changed_files(s,a,b,['refs/flow.md'])==['refs/flow.md']
    with pytest.raises(ValueError,match='AUTHORIZED'):changed_files(s,a,b,['SKILL.md'])


@pytest.mark.parametrize('files',[{'../outside':b'x'},{'/absolute':b'x'},{'a':b'x','A':b'x'},{'a/./b':b'x'},{'C:\\bad':b'x'}])
def test_paths_rejected(tmp_path,files):
    with pytest.raises(ValueError):freeze_package(Store(tmp_path/'state'),files)


def test_symlink_and_unsupported_mode_refused(tmp_path):
    s=Store(tmp_path/'state');root=tmp_path/'pkg';root.mkdir();(root/'SKILL.md').write_bytes(b'x');(root/'ref').symlink_to(root/'SKILL.md')
    with pytest.raises(ValueError,match='SYMLINK'):snapshot_package(s,root)
    with pytest.raises(ValueError,match='MODE'):freeze_package(s,{'SKILL.md':b'x'},{'SKILL.md':0o755})


def test_missing_original_package_transaction_never_falls_back_to_file_apply(tmp_path):
    from skill_observatory.owner_installers import SkillEvolutionInstaller
    s=Store(tmp_path/'state');marker=tmp_path/'unexpected-write';executable=tmp_path/'owner'
    executable.write_text('#!/bin/sh\nif [ "$1" = "--help" ]; then echo single-file-owner; else touch '+str(marker)+'; fi\n');executable.chmod(0o700)
    s.put('candidates',{'id':'c','parent_package':{'marker':'package'}})
    with pytest.raises(ValueError,match='OWNER_PACKAGE_TRANSACTION_UNAVAILABLE'):SkillEvolutionInstaller(str(executable)).apply(s,'c')
    assert not marker.exists() and not s.list('installations')


@pytest.mark.parametrize('available', [False, True])
def test_package_request_checks_exact_owner_surface_before_preparation(tmp_path, available):
    from skill_observatory.owner_installers import prepare_package_change,SkillEvolutionInstaller
    executable=tmp_path/'owner';marker=tmp_path/'unexpected-write'
    help_text='package-propose package-apply package-rollback' if available else 'single-file-owner'
    executable.write_text('#!/bin/sh\nif [ "$1" = "--help" ]; then echo '+help_text+'; else touch '+str(marker)+'; fi\n');executable.chmod(0o700)
    installer=SkillEvolutionInstaller(str(executable))
    s=Store(tmp_path/'state');root=tmp_path/'pkg';root.mkdir();(root/'SKILL.md').write_bytes(b'old')
    before=snapshot_package(s,root);after=freeze_package(s,{'SKILL.md':b'new'});proof=s.artifact(b'fixture owner grant')
    grant={'id':'g','status':'authorized','owner':'skill-evolution-loop','target':str(root),'surface':'package','evidence_sha256':proof,
           'changed_files':['SKILL.md'],'parent_package_digest':before['package_digest'],'candidate_package_digest':after['package_digest']};s.put('authority_grants',grant)
    value={'id':'r','owner':'skill-evolution-loop','target_root':str(root),'parent_package':before,'candidate_package':after,'changed_files':['SKILL.md'],'authority_id':'g'}
    r=prepare_package_change(s,value,installer);assert r['status']==('prepared' if available else 'blocked') and not r['automatic_apply']
    assert not marker.exists()
    (root/'SKILL.md').write_bytes(b'unrelated edit')
    with pytest.raises(ValueError,match='PARENT_DRIFT'):prepare_package_change(s,{**value,'id':'new'},installer)
    assert (root/'SKILL.md').read_bytes()==b'unrelated edit'


def test_exact_private_mode_is_part_of_package_authority(tmp_path):
    s=Store(tmp_path/'state');root=tmp_path/'pkg';root.mkdir();file=root/'SKILL.md';file.write_bytes(b'same bytes');file.chmod(0o600)
    private=snapshot_package(s,root);assert private['entries'][0]['mode']==0o600
    file.chmod(0o644);readable=snapshot_package(s,root)
    assert private['package_digest']!=readable['package_digest']
    with pytest.raises(ValueError,match='AUTHORIZED'):changed_files(s,private,readable,[])
    file.chmod(0o666)
    with pytest.raises(ValueError,match='MODE_REJECTED'):snapshot_package(s,root)
