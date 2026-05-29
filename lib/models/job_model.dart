class Job {
  final int? id;
  final String title;
  final String organization;
  final String totalVacancies;
  final DateTime? startDate;
  final DateTime lastDate;
  final String feeDetails;
  final String eligibility;
  final String officialApplyLink;

  Job({
    this.id,
    required this.title,
    required this.organization,
    required this.totalVacancies,
    this.startDate,
    required this.lastDate,
    required this.feeDetails,
    required this.eligibility,
    required this.officialApplyLink,
  });

  factory Job.fromJson(Map<String, dynamic> json) {
    return Job(
      id: json['id'] as int?,
      title: json['title'] as String,
      organization: json['organization'] as String,
      totalVacancies: json['total_vacancies'] as String,
      startDate: json['start_date'] != null
          ? DateTime.parse(json['start_date'] as String)
          : null,
      lastDate: DateTime.parse(json['last_date'] as String),
      feeDetails: json['fee_details'] as String,
      eligibility: json['eligibility'] as String,
      officialApplyLink: json['official_apply_link'] as String,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'organization': organization,
      'total_vacancies': totalVacancies,
      'start_date': startDate?.toIso8601String().split('T')[0],
      'last_date': lastDate.toIso8601String().split('T')[0],
      'fee_details': feeDetails,
      'eligibility': eligibility,
      'official_apply_link': officialApplyLink,
    };
  }
}