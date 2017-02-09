transformation_params = {
    'highcut': 180,
    'lowcut': 0.1,
    'nfreq_bands': 8,
    'win_length_sec': 60,
    'features': 'meanlog',
    'stride_sec': 60,
}

svm_params = {
    'C': 100,
    'kernel': 'rbf',
    'gamma': 0.01,
    'probability': False
}